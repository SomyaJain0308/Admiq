import time
import logging
import uuid
import threading    
from collections import deque
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI # NOTE: IN PRODUCTION CHANGE TO DeepSeek too
from langsmith import traceable
from backend.rag.config import get_settings
from backend.rag.retrieval import build_system_prompt, SYSTEM_PROMPT
from backend.schemas.models import AgentState, AgentTurnOutput
from backend.rag.monitoring import AGENT_REQUESTS, AGENT_ERRORS, AGENT_RETRIES, STAGE_LATENCY, RETRIEVAL_LATENCY, INVOKE_LATENCY, LLM_INPUT_TOKENS, LLM_OUTPUT_TOKENS, SOURCES_PER_RESPONSE, STUDENT_TOKEN_BUDGET_REJECTIONS, STUDENTS_TRACKED_ACTIVE
from backend.services.agent_helpers import extract_token_usage, classify_error, parse_source_csv



logger = logging.getLogger(__name__)



class PerStudentTokenBudget: # Rate Limiting is being tracked for every student in RAM if u think there is issue with it later u can change it idk.
    def __init__(self, max_tokens: int, window_seconds: float):
        self.max_tokens = max_tokens
        self.window_seconds = window_seconds
        self._events: dict[int, deque[tuple[float, int]]] = {} # self._events[42] might look like deque([(1000.1, 500), (1000.4, 300)]) — student 42 used 500 tokens at time 1000.1, then 300 more at time 1000.4.
        self._lock = threading.Lock() # One request at a time


    def _evict_state_locked(self, student_id: int, now: float) -> None: # Removal of all the convos outisde of the window_seconds timestamp
        dq = self._events.get(student_id)
        if dq is None:
            return
        while dq and now - dq[0][0] > self.window_seconds:
            dq.popleft()
        if not dq:
            del self._events[student_id]


    def record(self, student_id: int, tokens: int) -> None: # log that a student just used some tokens
        if tokens <= 0:
            return
        with self._lock:
            now = time.monotonic()
            self._events.setdefault(student_id, deque()).append((now, tokens))
            self._evict_state_locked(student_id, now)
            STUDENTS_TRACKED_ACTIVE.set(len(self._events))


    def is_exceeded(self, student_id: int) -> bool:
        with self._lock:
            now = time.monotonic()
            self._evict_state_locked(student_id, now)
            dq = self._events.get(student_id)
            usage = sum(t for _, t in dq) if dq else 0
            STUDENTS_TRACKED_ACTIVE.set(len(self._events))
            return usage >= self.max_tokens
        



class ProductionAgent:
    def __init__(self): # Loads settings (get_settings()), builds the graph, and sets max_retries / retrieval_k, start two llm instances(with structured json output)
        try:
            settings = get_settings()
            self.max_primary_retries = settings.max_primary_retries
            self.max_fallback_retries = settings.max_fallback_retries
            self.retrieval_k = getattr(settings, "retrieval_k", 5)
            self.primary_llm = ChatGoogleGenerativeAI(model=settings.primary_model, temperature=0, timeout=30, max_retries=0, api_key=settings.gemini_api_key).with_structured_output(AgentTurnOutput, method="json_schema", include_raw=True) # NOTE: IN PRODUCTION CHANGE TO DeepSeek  # We handle retries ourselves inside .env
            self.fallback_llm = ChatGoogleGenerativeAI(model=settings.fallback_model, temperature=0, timeout=30, max_retries=0, api_key=settings.gemini_api_key).with_structured_output(AgentTurnOutput, method="json_schema", include_raw=True)
            self.graph = self._build_graph()
        except Exception:
            logger.critical("ProductionAgent failed to initialize", exc_info=True)
            raise # Fail fast at startup rather than with a half-built agent.


    def _build_graph(self): # LangGraph state machine
        def retrieve(state: AgentState) -> dict: # Retrieve k(5) relevant chunks add them to system prompt including college_context, student_summary, session_summary, college_name, query then update agentState(prompt) in order to later send this system prompt to the llm
            try:
                prompt = build_system_prompt(db=state["db"], query=state["query"], college_id=state["college_id"], student_id=state["student_id"], session_id=state["session_id"], k=self.retrieval_k)
            except Exception as e:
                logger.warning("Retrieval failed, using default prompt college_id=%s student_id=%s session_id=%s error=%s k=%s", state["college_id"], state["student_id"], state["session_id"], e, k=self.retrieval_k, exc_info=True)
                prompt = SYSTEM_PROMPT.format(college_name="an", student_summary="No long-term student summary yet. OR error loading summary", session_summary="No current session summary yet. OR error loading session_summary", college_context="No official context available right now. or error loading college_context", previous_assistant_message="This is the start of the conversation, no previous message yet. OR error loading previous assistant message", query=state["query"], relevant_documents="No relevant documents were found for this query. OR error loading relevant_documents in this case don't invent any numbers or anything just try to be helpfull as a genuine assistant who is like day 1 at the job.")
            return {"prompt": prompt}


        @traceable(name="primary_llm_call", run_type="llm")
        def process_message(state: AgentState) -> dict: # Take the prompt from agentstate and send it to the llm then take it's response which includes raw response, sources, update_session_memmory save them in agentstate if there is an error add 1 to the error counter
            attempt = state["primary_retry_count"] + 1
            start = time.perf_counter()
            try:
                response = self.primary_llm.invoke(state["prompt"]) # returns {"raw": <OG AIMessage>, "parsed": <AgentTurnOutput instance if parsing succeeded>, "parsing_error": <if parsing failed then an error otherwise ''>}
                if response["parsing_error"] is not None:
                    raise ValueError(f"structured parse failed: {response['parsing_error']}") # NOTE: wtf am I raising an error
                parsed_response = response["parsed"]
                input_tokens, output_tokens = extract_token_usage(response["raw"])
                logger.info("Primary model succeeded attempt=%d elapsed_ms=%.0f seession_id=%s", attempt, (time.perf_counter() - start) * 1000, state["session_id"])
                return {"response": parsed_response.response, "updated_session_summary": parsed_response.updated_session_summary, "sources": parsed_response.sources, "error": None, "model_used": "primary", "input_tokens": input_tokens, "output_tokens": output_tokens}
            except Exception as e:
                logger.warning("Primary model failed attempt=%d session_id=%s error=%s", attempt, state["session_id"], e, exc_info=True)
                return {"error": str(e), "primary_retry_count": attempt, "model_used": ""}

            
        @traceable(name="fallback_llm_call", run_type="llm")
        def try_fallback(state: AgentState) -> dict: # fallback for the first llm everything is same except the model ofcourse
            attempt = state["fallback_retry_count"] + 1
            start = time.perf_counter()
            try:
                response = self.fallback_llm.invoke(state["prompt"])
                if response["parsing_error"] is not None:
                    raise ValueError(f"structured parse failed: {response['parsing_error']}") # NOTE: is there not a better alternative than raising an error
                parsed_response = response["parsed"]
                input_tokens, output_tokens = extract_token_usage(response["raw"])
                logger.info("Fallback model succeeded attempt=%d elapsed_ms=%.0f session_id=%s", attempt, (time.perf_counter() - start) * 1000, state["session_id"])
                return {"response": parsed_response.response, "updated_session_summary": parsed_response.updated_session_summary, "sources": parsed_response.sources, "error": None, "model_used": "fallback", "input_tokens": input_tokens, "output_tokens": output_tokens}
            except Exception as e:
                logger.warning("Fallback model failed attempt=%d session_id=%s error=%s", attempt, state["session_id"], e, exc_info=True)
                return {"error": str(e), "fallback_retry_count": attempt, "model_used": ""}
            

        def handle_error(state: AgentState) -> dict: # If this needs a comment then print("hello world") does too
            logger.error("Both primary and fallback exhausted session_id=%s college_id=%s primary_attempts=%s fallback_attempts=%s last_error=%s", state["session_id"], state["college_id"], state["primary_retry_count"], state["fallback_retry_count"], state.get("error"))
            return {"response": "I'm sorry, I'm having trouble processing your request right now. Please try again in a moment.", "updated_session_summary": "", "sources": "", "model_used": "error_handler"}
        

        def route_after_process(state: AgentState) -> str: # Determine what happened when primary model was invoked and decide next step
            if state.get("error") is None:
                return "done"
            elif state["primary_retry_count"] <= self.max_primary_retries:
                return "retry_process"
            else:
                return "fallback"
            

        def route_after_fallback(state: AgentState) -> str: # Determine what happened when fallback model was invoked and decide next step
            if state.get("error") is None:
                return "done"
            elif state["fallback_retry_count"] < self.max_fallback_retries:
                return "retry_fallback"
            else:
                return "error"
        

        graph = StateGraph(AgentState) # Invoke the graph nodes.

        graph.add_node("retrieve", retrieve)
        graph.add_node("process", process_message)
        graph.add_node("fallback", try_fallback)
        graph.add_node("error", handle_error)

        graph.add_edge(START, "retrieve")
        graph.add_edge("retrieve", "process")

        graph.add_conditional_edges("process", route_after_process, {"done": END, "retry_process": "process", "fallback": "fallback"})
        graph.add_conditional_edges("fallback", route_after_fallback, {"done": END, "retry_fallback": "fallback" , "error": "error"},)
        
        graph.add_edge("error", END)

        return graph.compile()
    
    @traceable(name="production_agent_invoke")
    def invoke(self, db, message: str, college_id: int, student_id: int, session_id: int, student_summary: str | None = None, session_summary: str | None = None) -> dict:
        try:
            result = self.graph.invoke({"db": db, "college_id": college_id, "student_id": student_id, "session_id": session_id, "query": message, "error": None, "primary_retry_count": 0, "fallback_retry_count": 0, "model_used": "0", "sources": None, "student_summary": student_summary, "session_summary": session_summary}, config={"tags": ["prodcution_agent"], "metadata": {"college_id": college_id, "student_id": student_id, "session_id": session_id}})
        except Exception:
            logger.critical("Graph invocation crashed unexpectedly college_id=%s student_id=%s session_id=%s", college_id, student_id, session_id, exc_info=True)
            return {"response": "I'm sorry, I'm having trouble processing your request right now. Please try again in a moment.", "updated_session_summary": "", "model_used": "crash_handler", "error": "unhandled_graph_exception", "sources": []}
    
        return {"response": result["response"], "updated_session_summary": result["updated_session_summary"], "model_used": result.get("model_used", "unknown"), "error": result.get("error"), "sources": result.get("sources", []), "input_tokens": result.get("input_tokens", 0), "output_tokens": result.get("output_tokens", 0)}