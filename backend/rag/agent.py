from typing import Optional, TypedDict, Annotated, List
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langsmith import traceable
from rag.config import get_settings
from rag.retrieval import retrieve_context, format_context, SYSTEM_PROMPT
from rag.checkpointer import get_checkpointer


RAG_CONTEXT_MESSAGE_ID = "rag_context" # Fixed id so add_messages can overwrite it instead of stacking a new system prompt every message


class AgentState(TypedDict): # dictionary that gets passed from node to node, and each node can read it and add to it.
    messages: Annotated[list[BaseMessage], add_messages]
    error: Optional[str]
    retry_count: int
    model_used: str
    sources: List[str]



class ProductionAgent:

    def __init__(self):
        settings = get_settings()
        self.checkpointer = get_checkpointer()
        self.graph = self._build_graph()
        self.max_retries = get_settings().max_retries
        self.retrieval_k = getattr(settings, "retrieval_k", 5)
        self.primary_llm = ChatGoogleGenerativeAI(
            model=settings.primary_model,
            temperature=0,
            timeout=30,
            max_retries=0, # We handle retries ourseves
            api_key=settings.gemini_api_key,
        )
        self.fallback_llm = ChatGoogleGenerativeAI( # IN PRODUCTION CHANGE TO ANOTHER MODEL
            model=settings.fallback_model,
            temperature=0,
            timeout=30,
            max_retries=0,
            api_key=settings.gemini_api_key, # IN PRODUCTION CHANGE TO ANOTHER MODEL
        )
    
    @staticmethod
    def _extract_text(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        return str(content)
        

    @staticmethod
    def _ordered_for_llm(messages: list[BaseMessage]) ->list[BaseMessage]:
        system_msgs = []
        other_msgs =[]
        for m in messages:
            if isinstance(m, SystemMessage):
                system_msgs.append(m)
            else:
                other_msgs.append(m)
        return system_msgs + other_msgs


    def _build_graph(self): # LangGraph state machine


        def retrieve(state: AgentState) -> dict:
            latest_message = state["messages"][-1]
            query = self._extract_text(latest_message.content)

            try:
                documents = retrieve_context(query, k=self.retrieval_k)
            except Exception as e:
                documents = []
            
            context = format_context(documents)
            system_content = SYSTEM_PROMPT.format(context=context)

            sources = [] # If two chunks have the same source don't mention the source more than once
            for doc in documents:
                source = doc.metadata.get("source")
                if source and source not in sources:
                    sources.append(source)

            return {
                "messages": [SystemMessage(id=RAG_CONTEXT_MESSAGE_ID, content=system_content)],
                "sources": sources,
            }
        

        def process_message(state: AgentState) -> dict:
            try:
                ordered = self._ordered_for_llm(state["messages"])
                response = self.primary_llm.invoke(ordered)
                return{
                    "messages": [response],
                    "error": None,
                    "model_used": "primary"
                }
            except Exception as e:
                return {
                    "error": str(e),
                    "retry_count": state["retry_count"] + 1,
                    "model_used": "",
                }
        def try_fallback(state: AgentState) -> dict:
            try:
                ordered = self._ordered_for_llm(state["messages"])
                response = self.fallback_llm.invoke(ordered)
                return{
                    "messages": [response],
                    "error": None,
                    "model_used": "fallback"
                }
            except Exception as e:
                return {
                    "error": str(e),
                    "model_used": "",
                }
        def handle_error(state: AgentState) -> dict:
            return {
                    "messages": [AIMessage(content=("I'm sorry, I'm having trouble processing your request right now. Please try again in a moment."))],
                    "model_used": "error_handler",
            }
        

        def route_after_process(state: AgentState) -> str: # Decide what to do when primary model fails
            if state.get("error") is None:
                return "done"
            elif state["retry_count"] < self.max_retries:
                return "fallback"
            else:
                return "error"
        def route_after_fallback(state: AgentState) -> str:
            if state.get("error") is None:
                return "done"
            else:
                return "error"
        

        graph = StateGraph(AgentState) # Invoke the graph nodes.

        graph.add_node("retrieve", retrieve)
        graph.add_node("process", process_message)
        graph.add_node("fallback", try_fallback)
        graph.add_node("error", handle_error)

        graph.add_edge(START, "retrieve")
        graph.add_edge("retrieve", "process")

        graph.add_conditional_edges(
            "process",
            route_after_process,
            {"done": END, "fallback": "fallback", "error": "error"},
            )
        graph.add_conditional_edges(
            "fallback",
            route_after_fallback,
            {"done": END, "error": "error"},
        )
        graph.add_edge("error", END)

        return graph.compile(checkpointer=self.checkpointer)
    
    @traceable(name="production_agent_invoke")
    def invoke(self, message: str, thread_id: str = "default") -> dict:
        result = self.graph.invoke({ # Look inside of self.graph and then invoke the graph(nodes) starting from graph = StateGraph(AgentState)
            "messages": [HumanMessage(content=message)],
            "error": None,
            "retry_count": 0,
            "model_used": "0",
            "sources": [],
        },
        config={"configurable": {"thread_id": thread_id}}
        )

        return {
            "response": self._extract_text(result["messages"][-1].content),
            "model_used": result.get("model_used", "unknown"),
            "error": result.get("error"),
            "sources": result.get("sources", []),
        }