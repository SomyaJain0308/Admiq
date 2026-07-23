import time
import logging
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI # NOTE: IN PRODUCTION CHANGE TO DeepSeek too
from langsmith import traceable
from backend.rag.config import get_settings
from backend.rag.retrieval import build_system_prompt, SYSTEM_PROMPT
from backend.schemas.models import AgentState, AgentTurnOutput
from backend.rag.monitoring import AGENT_REQUESTS, AGENT_ERRORS, AGENT_RETRIES, STAGE_LATENCY, RETRIEVAL_LATENCY, INVOKE_LATENCY, LLM_INPUT_TOKENS, LLM_OUTPUT_TOKENS, SOURCES_PER_RESPONSE
from backend.services.agent_helpers import extract_token_usage, classify_error

logger = logging.getLogger(__name__)


class ProductionAgent:
    def __init__(self): # Loads settings (get_settings()), builds the graph, and sets max_retries / retrieval_k, start two llm instances(with structured json output)
        try:
            settings = get_settings()
            self.max_primary_retries = settings.max_primary_retries
            self.max_fallback_retries = settings.max_fallback_retries
            self.retrieval_k = getattr(settings, "retrieval_k", 5)
            self.primary_llm = ChatGoogleGenerativeAI(model=settings.primary_model, temperature=0, timeout=30, max_retries=0, api_key=settings.gemini_api_key).with_structured_output(AgentTurnOutput, method="json_schema", include_raw=True) # NOTE: IN PRODUCTION CHANGE TO DeepSeek  # We handle retries ourselves inside .env
            self.fallback_llm = ChatGoogleGenerativeAI(model=settings.fallback_model, temperature=0, timeout=30, max_retries=0, api_key=settings.gemini_api_key).with_structured_output(AgentTurnOutput, method="json_schema", include_raw=True)
            self.primary_llm_name = settings.primary_model
            self.fallback_llm_name = settings.fallback_model
            self.graph = self._build_graph()
        except Exception:
            logger.critical("ProductionAgent failed to initialize", exc_info=True)
            raise # Fail fast at startup rather than with a half-built agent.


    def _build_graph(self): # LangGraph state machine
        def retrieve(state: AgentState) -> dict: # Retrieve k(5) relevant chunks add them to system prompt including college_context, student_summary, session_summary, college_name, query then update agentState(prompt) in order to later send this system prompt to the llm
            start = time.perf_counter()
            try:
                prompt = build_system_prompt(db=state["db"], query=state["query"], college_id=state["college_id"], student_id=state["student_id"], session_id=state["session_id"], k=self.retrieval_k)
            except Exception as e:
                logger.warning("Retrieval failed, using default prompt college_id=%s student_id=%s session_id=%s error=%s k=%s", state["college_id"], state["student_id"], state["session_id"], e, k=self.retrieval_k, exc_info=True)
                prompt = SYSTEM_PROMPT.format(college_name="an", student_summary="No long-term student summary yet. OR error loading summary", session_summary="No current session summary yet. OR error loading session_summary", college_context="No official context available right now. or error loading college_context", previous_assistant_message="This is the start of the conversation, no previous message yet. OR error loading previous assistant message", query=state["query"], relevant_documents="No relevant documents were found for this query. OR error loading relevant_documents in this case don't invent any numbers or anything just try to be helpfull as a genuine assistant who is like day 1 at the job.")
            finally:
                RETRIEVAL_LATENCY.observe(time.perf_counter() - start)
            return {"prompt": prompt}


        @traceable(name="primary_llm_call", run_type="llm")
        def process_message(state: AgentState) -> dict: # Take the prompt from agentstate and send it to the llm then take it's response which includes raw response, sources, update_session_memmory save them in agentstate if there is an error add 1 to the error counter
            attempt = state["primary_retry_count"] + 1
            start = time.perf_counter()
            prev_input_tokens = state.get("input_tokens", 0)
            prev_output_tokens = state.get("output_tokens", 0)
            response = None
            try:
                response = self.primary_llm.invoke(state["prompt"]) # returns {"raw": <OG AIMessage>, "parsed": <AgentTurnOutput instance if parsing succeeded>, "parsing_error": <if parsing failed then an error otherwise ''>}
                if response["parsing_error"] is not None:
                    raise ValueError(f"structured parse failed: {response['parsing_error']}") # NOTE: wtf am I raising an error
                parsed_response = response["parsed"]
                input_tokens, output_tokens = extract_token_usage(response["raw"])
                total_input = prev_input_tokens + input_tokens
                total_output = prev_output_tokens + output_tokens
                LLM_INPUT_TOKENS.labels(stage="primary", model_used=self.primary_llm_name).inc(input_tokens) 
                LLM_OUTPUT_TOKENS.labels(stage="primary", model_used=self.primary_llm_name).inc(output_tokens)
                elapsed = time.perf_counter() - start
                STAGE_LATENCY.labels(stage="primary", model_used=self.primary_llm_name).observe(elapsed)
                logger.info("Primary model succeeded attempt=%d elapsed_ms=%.0f seession_id=%s", attempt, (time.perf_counter() - start) * 1000, state["session_id"])
                return {"response": parsed_response.response, "updated_session_summary": parsed_response.updated_session_summary, "sources": parsed_response.sources, "error": None, "model_used": "primary", "input_tokens": total_input, "output_tokens": total_output}
            except Exception as e:
                call_input_tokens = 0
                call_output_tokens = 0
                if response is not None:
                    call_input_tokens = extract_token_usage(response["raw"])
                    call_output_tokens = extract_token_usage(response["raw"])
                total_input = prev_input_tokens + call_input_tokens
                total_output = prev_output_tokens + call_output_tokens
                elapsed = time.perf_counter() - start
                STAGE_LATENCY.labels(stage="primary", model_used=self.primary_llm_name).observe(elapsed)
                AGENT_ERRORS.labels(stage="primary", error_type=classify_error(e)).inc()
                AGENT_RETRIES.labels(stage="primary").inc()
                LLM_INPUT_TOKENS.labels(stage="primary", model_used=self.primary_llm_name).inc(call_input_tokens)
                LLM_OUTPUT_TOKENS.labels(stage="primary", model_used=self.primary_llm_name).inc(call_input_tokens)
                logger.warning("Primary model failed attempt=%d session_id=%s error=%s", attempt, state["session_id"], e, exc_info=True)
                return {"error": str(e), "primary_retry_count": attempt, "model_used": "", "input_tokens": total_input, "output_tokens": total_output}

            
        @traceable(name="fallback_llm_call", run_type="llm")
        def try_fallback(state: AgentState) -> dict: # fallback for the first llm everything is same except the model ofcourse
            attempt = state["fallback_retry_count"] + 1
            start = time.perf_counter()
            response = None
            prev_input_tokens = 0
            prev_output_tokens = 0
            try:
                response = self.fallback_llm.invoke(state["prompt"])
                if response["parsing_error"] is not None:
                    raise ValueError(f"structured parse failed: {response['parsing_error']}") # NOTE: is there not a better alternative than raising an error
                parsed_response = response["parsed"]
                input_tokens, output_tokens = extract_token_usage(response["raw"])
                total_input = input_tokens + prev_input_tokens
                total_output = output_tokens + prev_output_tokens
                LLM_INPUT_TOKENS.labels(stage="fallback", model_used=self.fallback_llm_name).inc(input_tokens) 
                LLM_OUTPUT_TOKENS.labels(stage="fallback", model_used=self.fallback_llm_name).inc(output_tokens)
                elapsed = time.perf_counter() - start
                STAGE_LATENCY.labels(stage="fallback", model_used=self.fallback_llm_name).observe(elapsed)
                logger.info("Fallback model succeeded attempt=%d elapsed_ms=%.0f session_id=%s", attempt, (time.perf_counter() - start) * 1000, state["session_id"])
                return {"response": parsed_response.response, "updated_session_summary": parsed_response.updated_session_summary, "sources": parsed_response.sources, "error": None, "model_used": "fallback", "input_tokens": total_input, "output_tokens": total_output}
            except Exception as e:
                call_input_tokens = 0
                call_output_tokens = 0
                if response is not None:
                    call_input_tokens = extract_token_usage(response["raw"])
                    call_output_tokens = extract_token_usage(response["raw"])
                total_output = call_output_tokens + prev_output_tokens
                total_input = call_input_tokens + prev_input_tokens
                elapsed = time.perf_counter() - start
                STAGE_LATENCY.labels(stage="fallback", model_used=self.fallback_llm_name).observe(elapsed)
                AGENT_ERRORS.labels(stage="fallback", error_type=classify_error(e)).inc()
                AGENT_RETRIES.labels(stage="fallback").inc()
                LLM_INPUT_TOKENS.labels(stage="fallback", model_used=self.fallback_llm_name).inc(call_input_tokens)
                LLM_OUTPUT_TOKENS.labels(stage="fallback", model_used=self.fallback_llm_name).inc(call_output_tokens)
                logger.warning("Fallback model failed attempt=%d session_id=%s error=%s", attempt, state["session_id"], e, exc_info=True)
                return {"error": str(e), "fallback_retry_count": attempt, "model_used": "", "input_tokens": total_input, "output_tokens": total_output}
            

        def handle_error(state: AgentState) -> dict: # If this needs a comment then print("hello world") does too
            logger.error("Both primary and fallback exhausted session_id=%s college_id=%s primary_attempts=%s fallback_attempts=%s last_error=%s", state["session_id"], state["college_id"], state["primary_retry_count"], state["fallback_retry_count"], state.get("error"))
            return {"response": "I'm sorry, I'm having trouble processing your request right now. Please try again in a moment.", "updated_session_summary": "", "sources": "", "model_used": "error_handler", "input_tokens": state.get("input_tokens", 0), "output_tokens": state.get("output_tokens", 0)}
        

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
        start = time.perf_counter()
        try:
            result = self.graph.invoke({"db": db, "college_id": college_id, "student_id": student_id, "session_id": session_id, "query": message, "error": None, "primary_retry_count": 0, "fallback_retry_count": 0, "model_used": "0", "sources": None, "student_summary": student_summary, "session_summary": session_summary}, config={"tags": ["prodcution_agent"], "metadata": {"college_id": college_id, "student_id": student_id, "session_id": session_id}})
        except Exception:
            logger.critical("Graph invocation crashed unexpectedly college_id=%s student_id=%s session_id=%s", college_id, student_id, session_id, exc_info=True)
            AGENT_REQUESTS.labels(outcome="crash", model_used="none", error_type="unhandled_graph_exception").inc()
            INVOKE_LATENCY.observe(time.perf_counter() - start)
            return {"response": "I'm sorry, I'm having trouble processing your request right now. Please try again in a moment.", "updated_session_summary": "", "model_used": "crash_handler", "error": "unhandled_graph_exception", "sources": []}

        INVOKE_LATENCY.observe(time.perf_counter() - start)
        model_used = result.get("model_used", "unknown")
        error = result.get("error")
        if error is None and model_used != "error_handler":
            outcome = "success" 
            SOURCES_PER_RESPONSE.labels(model_used=model_used).observe(len(result.get("sources") or []))
        else:
            outcome = "error"
        AGENT_REQUESTS.labels(outcome=outcome, model_used=model_used, error_type=(classify_error(Exception(error)) if error else "")).inc()
        return {"response": result["response"], "updated_session_summary": result["updated_session_summary"], "model_used": result.get("model_used", "unknown"), "error": result.get("error"), "sources": result.get("sources", []), "input_tokens": result.get("input_tokens", 0), "output_tokens": result.get("output_tokens", 0)}