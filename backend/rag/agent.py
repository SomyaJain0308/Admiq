import time
import logging
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI # NOTE: IN PRODUCTION CHANGE TO DeepSeek too
from langsmith import traceable
from rag.config import get_settings
from rag.retrieval import RE_QUERY_PROMPT, SYSTEM_PROMPT, RESOLVE_QUERY_PROMPT, build_system_prompt, get_relevant_documents_scored, get_previous_assistant_message
from schemas.models import AgentState, AgentTurnOutput, QueryRewrite
from rag.monitoring import AGENT_REQUESTS, AGENT_ERRORS, AGENT_RETRIES, QUERY_DECOMPOSITION_SIZE, RETRIEVAL_ROUNDS_TO_RESOLVE, STAGE_LATENCY, RETRIEVAL_LATENCY, INVOKE_LATENCY, LLM_INPUT_TOKENS, LLM_OUTPUT_TOKENS, SOURCES_PER_RESPONSE, AGENT_MISSING_FOLLOWUP, RETRIEVAL_DISTANCE, SUBQUERIES_UNRESOLVED
from services.agent_helpers import extract_token_usage, classify_error

logger = logging.getLogger(__name__)


class ProductionAgent:
    def __init__(self): # Loads settings (get_settings()), builds the graph, and sets max_retries / retrieval_k, start two llm instances(with structured json output)
        try:
            settings = get_settings() # Defined in rag/config (values set in .env)

            self.primary_llm_name = settings.primary_model
            self.primary_llm = ChatGoogleGenerativeAI(model=settings.primary_model, temperature=0, timeout=30, max_retries=0, api_key=settings.gemini_api_key).with_structured_output(AgentTurnOutput, method="json_schema", include_raw=True) # NOTE: IN PRODUCTION CHANGE TO DeepSeek  # We handle retries ourselves inside .env
            self.max_primary_retries = settings.max_primary_retries

            self.fallback_llm_name = settings.fallback_model
            self.fallback_llm = ChatGoogleGenerativeAI(model=settings.fallback_model, temperature=0, timeout=30, max_retries=0, api_key=settings.gemini_api_key).with_structured_output(AgentTurnOutput, method="json_schema", include_raw=True)
            self.max_fallback_retries = settings.max_fallback_retries

            self.query_llm_name = settings.query_model
            self.query_llm = ChatGoogleGenerativeAI(model=settings.query_model, temperature=0, timeout=15, max_retries=0, api_key=settings.gemini_api_key).with_structured_output(QueryRewrite, method="json_schema", include_raw=True) # NOTE: IN PRODUCTION CHANGE TO DeepSeek 
            self.max_retrieval_retries = settings.max_retrieval_retries

            self.retrieval_distance_threshold = settings.retrieval_distance_threshold

            self.graph = self._build_graph()
        except Exception:
            logger.critical("ProductionAgent failed to initialize", exc_info=True)
            raise # Fail fast at startup rather than with a half-built agent.


    def _build_graph(self): # LangGraph state machine
        def resolve_query(state: AgentState) -> dict: # Pass the initial query to llm it will decide wheather to retrieve or not, if true then rewrite the query for perfect retrieval which is determined by route_after_resolve
            start = time.perf_counter()
            # A little off the topic but let's first store the previous_assitant_message
            try:
                previous_assistant_message = get_previous_assistant_message(db=state["db"], college_id=state["college_id"], student_id=state["student_id"]) # Defined in rag/retrieval.py
            except Exception as e:
                logger.warning("Failed to fetch previous_assistant_message college_id=%s student_id=%s session_id=%s error=%s", state["college_id"], state["student_id"], state["session_id"], e, exc_info=True)
                previous_assistant_message = "This is the start of the conversation, no previous messages yet."

            try:
                result = self.query_llm.invoke(RESOLVE_QUERY_PROMPT.format(query=state["query"], previous_assistant_message=previous_assistant_message)) # Prompt present in rag/retrieval.py

                input_tokens, output_tokens = extract_token_usage(result["raw"])
                needs_retrieval = result["parsed"].needs_retrieval
                search_queries = result["parsed"].search_queries or [state["query"]]

                if needs_retrieval:
                    QUERY_DECOMPOSITION_SIZE.observe(len(search_queries))
            except Exception as e:
                logger.warning("resolve_query failed college_id=%s student_id=%s session_id=%s error=%s", state["college_id"], state["student_id"], state["session_id"], e, exc_info=True)
                search_queries, input_tokens, output_tokens = [state["query"]], 0, 0
                needs_retrieval = True
            STAGE_LATENCY.labels(stage="resolve_query", model_used=self.query_llm_name).observe(time.perf_counter() - start)
            LLM_INPUT_TOKENS.labels(stage="resolve_query", model_used=self.query_llm_name).inc(input_tokens)
            LLM_OUTPUT_TOKENS.labels(stage="resolve_query", model_used=self.query_llm_name).inc(output_tokens)

            result_dict = {"pending_queries": search_queries if needs_retrieval else [], "needs_retrieval": needs_retrieval, "resolved_chunks": [], "previous_assistant_message": previous_assistant_message, "input_tokens": state.get("input_tokens", 0) + input_tokens, "output_tokens": state.get("output_tokens", 0) + output_tokens, "retrieval_retry_count": 0}
            if not needs_retrieval:
                result_dict["relevant_documents"] = "No document lookup needed - this is a greeting, thanks, or small talk, not an admissions question."
            return result_dict


        def _k_for_query_count(n: int) -> int: # Determine how many chunks per sub query to fetch by looking at number of sub queries.
            if n <= 1:
                return 3
            elif n <= 3:
                return 2
            else:
                return 1


        def retrieve(state: AgentState) -> dict: # If needs_retrieve = True then search k chunks for each sub-query with their cosine distance if > retrieval_distance_threshold disregard those queries then send to resolve_after_resolve
            start = time.perf_counter()
            try:
                pending = state["pending_queries"]
                k = _k_for_query_count(len(pending))
                already_seen_ids = {chunk_id for chunk_id, _, _ in state.get("resolved_chunks", [])}
                newly_resolved = list(state.get("resolved_chunks", []))
                still_pending = []
                for sub_query in pending:
                    scored = get_relevant_documents_scored(db=state["db"], query=sub_query, college_id=state["college_id"], k=k) # Defined in rag/retrieval.py
                    for chunk_id, _, dist in scored:
                        RETRIEVAL_DISTANCE.labels(passed_threshold=str(dist <= self.retrieval_distance_threshold).lower()).observe(dist)
                    passing = [(chunk_id, block, distance) for chunk_id, block, distance in scored if distance <= self.retrieval_distance_threshold and chunk_id not in already_seen_ids]
                    if passing:
                        for chunk_id, _, dist in passing:
                            already_seen_ids.add(chunk_id)
                        newly_resolved.extend(passing)
                    else:
                        still_pending.append(sub_query)
                if newly_resolved:
                    relevant_documents = "\n---\n".join(block for _, block, _ in newly_resolved)
                    best_distance = min(dist for _, _, dist in newly_resolved)
                else:
                    relevant_documents = "No relevant documents were found for this query."
                    best_distance = 1.0
            except Exception as e:
                logger.warning("Retrieval failed college_id=%s student_id=%s session_id=%s error=%s", state["college_id"], state["student_id"], state["session_id"], e, exc_info=True)
                newly_resolved, still_pending = state.get("resolved_chunks", []), state.get("pending_queries", [])
                relevant_documents, best_distance = "No relevant documents were found for this query.", 1.0
            finally:
                RETRIEVAL_LATENCY.observe(time.perf_counter() - start)
            return {"resolved_chunks": newly_resolved, "pending_queries": still_pending, "relevant_documents": relevant_documents, "best_distance": best_distance}


        def re_query(state: AgentState):
            attempt = state["retrieval_retry_count"] + 1
            start = time.perf_counter()
            failed = state["pending_queries"]
            try:
                result = self.query_llm.invoke(RE_QUERY_PROMPT.format(original_query=state["query"], failed_queries="\n".join(failed), previous_assistant_message=state["previous_assistant_message"]))
                input_tokens, output_tokens = extract_token_usage(result["raw"])
                new_queries = result["parsed"].search_queries
                if len(new_queries) != len(failed):
                    new_queries = failed
            except Exception as e:
                logger.warning("re-query failed college_id=%s studnet_id=%s session_id=%s error=%s", state["college_id"], state["student_id"], state["session_id"], e, exc_info=True)
                new_queries, input_tokens, output_tokens = failed, 0, 0
            STAGE_LATENCY.labels(stage="re_query", model_used=self.query_llm_name).observe(time.perf_counter() - start)
            LLM_INPUT_TOKENS.labels(stage="re_query", model_used=self.query_llm_name).inc(input_tokens)
            LLM_OUTPUT_TOKENS.labels(stage="re_query", model_used=self.query_llm_name).inc(output_tokens)
            logger.info("Re-querying attempt=%d college_id=%s student_id=%s session_id=%s old=%r new=%r", attempt, state["college_id"], state["student_id"], state["session_id"], failed, new_queries)
            return {"pending_queries": new_queries, "retrieval_retry_count": attempt, "input_tokens": state.get("input_tokens", 0) + input_tokens, "output_tokens": state.get("output_tokens", 0) + output_tokens}


        def flag_low_confidence(state: AgentState) -> dict:
            logger.warning("Retrieval exhausted retries college_id=%s student_id=%s session_id=%s query=%r best_distance=%.3f", state["college_id"], state["student_id"], state["session_id"], state["query"], state["best_distance"])
            SUBQUERIES_UNRESOLVED.observe(len(state["pending_queries"]))
            return {"needs_human_review": True}


        def build_prompt(state: AgentState) -> dict:
            try:
                prompt = build_system_prompt(db=state["db"], query=state["query"], college_id=state["college_id"], student_id=state["student_id"], session_id=state["session_id"], relevant_documents=state["relevant_documents"], student_summary=state.get("student_summary"), session_summary=state.get("session_summary"))
            except Exception as e:
                logger.warning("build_system_prompt failed, using default prompt college_id=%s student_id=%s session_id=%s error=%s", state["college_id"], state["student_id"], state["session_id"], e, exc_info=True)
                prompt = SYSTEM_PROMPT.format(college_name="an", student_summary=state.get("student_summary") or "No long-term student summary yet. OR error loading summary", session_summary=state.get("session_summary") or "No current session summary yet. OR error loading session_summary", college_context="No official context available right now. or error loading college_context", previous_assistant_message="This is the start of the conversation, no previous message yet. OR error loading previous assistant message", query=state["query"], relevant_documents=state.get("relevant_documents") or "No relevant documents were found for this query.")
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
                    raise ValueError(f"structured parse failed: {response['parsing_error']}") # NOTE: if it's the correct langgraph syntax then it will work otherwise it will raise an error test and change from the error format in production.
                parsed_response = response["parsed"]
                input_tokens, output_tokens = extract_token_usage(response["raw"])
                total_input = prev_input_tokens + input_tokens
                total_output = prev_output_tokens + output_tokens
                LLM_INPUT_TOKENS.labels(stage="primary", model_used=self.primary_llm_name).inc(input_tokens) 
                LLM_OUTPUT_TOKENS.labels(stage="primary", model_used=self.primary_llm_name).inc(output_tokens)
                STAGE_LATENCY.labels(stage="primary", model_used=self.primary_llm_name).observe(time.perf_counter() - start)
                logger.info("Primary model succeeded attempt=%d elapsed_ms=%.0f college_id=%s student_id=%s session_id=%s", attempt, (time.perf_counter() - start) * 1000, state["college_id"], state["student_id"], state["session_id"])
                if not parsed_response.response.strip().endswith("?"):
                    AGENT_MISSING_FOLLOWUP.labels(model_used="primary").inc()
                    logger.info("Response missing follow-up question college_id=%s student_id=%s session_id=%s response=%r", state["college_id"], state["student_id"], state["session_id"], parsed_response.response[-80:])
                return {"response": parsed_response.response, "updated_session_summary": parsed_response.updated_session_summary, "sources": parsed_response.sources, "error": None, "model_used": "primary", "input_tokens": total_input, "output_tokens": total_output, "wants_human_handoff": parsed_response.wants_human_handoff or state.get("needs_human_review", False)}
            except Exception as e:
                call_input_tokens = 0
                call_output_tokens = 0
                if response is not None:
                    call_input_tokens, call_output_tokens = extract_token_usage(response["raw"])
                total_input = prev_input_tokens + call_input_tokens
                total_output = prev_output_tokens + call_output_tokens
                STAGE_LATENCY.labels(stage="primary", model_used=self.primary_llm_name).observe(time.perf_counter() - start)
                AGENT_ERRORS.labels(stage="primary", error_type=classify_error(e)).inc()
                AGENT_RETRIES.labels(stage="primary").inc()
                LLM_INPUT_TOKENS.labels(stage="primary", model_used=self.primary_llm_name).inc(call_input_tokens)
                LLM_OUTPUT_TOKENS.labels(stage="primary", model_used=self.primary_llm_name).inc(call_output_tokens)
                logger.warning("Primary model failed attempt=%d college_id=%s student_id=%s session_id=%s error=%s", attempt, state["college_id"], state["student_id"], state["session_id"], e, exc_info=True)
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
                STAGE_LATENCY.labels(stage="fallback", model_used=self.fallback_llm_name).observe(time.perf_counter() - start)
                logger.info("Fallback model succeeded attempt=%d elapsed_ms=%.0f college_id=%s student_id=%s session_id=%s", attempt, (time.perf_counter() - start) * 1000, state["college_id"], state["student_id"], state["session_id"])
                if not parsed_response.response.strip().endswith("?"):
                    AGENT_MISSING_FOLLOWUP.labels(model_used="fallback").inc()
                    logger.info("Response missing follow-up question college_id=%s student_id=%s session_id=%s response=%r", state["college_id"], state["student_id"], state["session_id"], parsed_response.response[-80:])
                return {"response": parsed_response.response, "updated_session_summary": parsed_response.updated_session_summary, "sources": parsed_response.sources, "error": None, "model_used": "fallback", "input_tokens": total_input, "output_tokens": total_output, "wants_human_handoff": parsed_response.wants_human_handoff or state.get("needs_human_review", False)}
            except Exception as e:
                call_input_tokens = 0
                call_output_tokens = 0
                if response is not None:
                    call_input_tokens, call_output_tokens = extract_token_usage(response["raw"])
                total_output = call_output_tokens + prev_output_tokens
                total_input = call_input_tokens + prev_input_tokens
                STAGE_LATENCY.labels(stage="fallback", model_used=self.fallback_llm_name).observe(time.perf_counter() - start)
                AGENT_ERRORS.labels(stage="fallback", error_type=classify_error(e)).inc()
                AGENT_RETRIES.labels(stage="fallback").inc()
                LLM_INPUT_TOKENS.labels(stage="fallback", model_used=self.fallback_llm_name).inc(call_input_tokens)
                LLM_OUTPUT_TOKENS.labels(stage="fallback", model_used=self.fallback_llm_name).inc(call_output_tokens)
                logger.warning("Fallback model failed attempt=%d college_id=%s student_id=%s session_id=%s error=%s", attempt, state["college_id"], state["student_id"], state["session_id"], e, exc_info=True)
                return {"error": str(e), "fallback_retry_count": attempt, "model_used": "", "input_tokens": total_input, "output_tokens": total_output}
            

        def handle_error(state: AgentState) -> dict: # If this needs a comment then print("hello world") does too
            logger.error("Both primary and fallback exhausted session_id=%s college_id=%s student_id=%s primary_attempts=%s fallback_attempts=%s last_error=%s", state["session_id"], state["college_id"], state["student_id"], state["primary_retry_count"], state["fallback_retry_count"], state.get("error"))
            return {"response": "I'm sorry, I'm having trouble processing your request right now. Please try again in a moment.", "updated_session_summary": "", "sources": "", "model_used": "error_handler", "input_tokens": state.get("input_tokens", 0), "output_tokens": state.get("output_tokens", 0)}


        def route_after_resolve(state: AgentState) -> str:
            return "retrieve" if state["needs_retrieval"] else "skip_retrieval"
        

        def route_after_retrieve(state: AgentState) -> str:
            if not state["pending_queries"]:
                RETRIEVAL_ROUNDS_TO_RESOLVE.observe(state["retrieval_retry_count"])
                return "generate"
            elif state["retrieval_retry_count"] < self.max_retrieval_retries:
                return "re_query"
            else:
                return "flag_and_generate"


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

        graph.add_node("resolve_query", resolve_query)
        graph.add_node("retrieve", retrieve)
        graph.add_node("re_query", re_query)
        graph.add_node("flag_low_confidence", flag_low_confidence)
        graph.add_node("build_prompt", build_prompt)
        graph.add_node("process", process_message)
        graph.add_node("fallback", try_fallback)
        graph.add_node("error", handle_error)

        graph.add_edge(START, "resolve_query")
        graph.add_conditional_edges("resolve_query", route_after_resolve, {"retrieve": "retrieve", "skip_retrieval": "build_prompt"})
        graph.add_conditional_edges("retrieve", route_after_retrieve, {"generate": "build_prompt", "re_query": "re_query", "flag_and_generate": "flag_low_confidence"})
        graph.add_edge("re_query", "retrieve")
        graph.add_edge("flag_low_confidence", "build_prompt")
        graph.add_edge("build_prompt", "process")
        graph.add_conditional_edges("process", route_after_process, {"done": END, "retry_process": "process", "fallback": "fallback"})
        graph.add_conditional_edges("fallback", route_after_fallback, {"done": END, "retry_fallback": "fallback" , "error": "error"},)
        graph.add_edge("error", END)

        return graph.compile()
    
    @traceable(name="production_agent_invoke")
    def invoke(self, db, message: str, college_id: int, student_id: int, session_id: int, student_summary: str | None = None, session_summary: str | None = None) -> dict:
        start = time.perf_counter()
        try:
            result = self.graph.invoke({"db": db, "college_id": college_id, "student_id": student_id, "session_id": session_id, "query": message, "error": None, "primary_retry_count": 0, "fallback_retry_count": 0, "retrieval_retry_count": 0, "model_used": "0", "sources": None, "student_summary": student_summary, "session_summary": session_summary, "input_tokens": 0, "output_tokens": 0, "needs_human_review": False, "wants_human_handoff": False}, config={"tags": ["prodcution_agent"], "metadata": {"college_id": college_id, "student_id": student_id, "session_id": session_id}})
        except Exception:
            logger.critical("Graph invocation crashed unexpectedly college_id=%s student_id=%s session_id=%s", college_id, student_id, session_id, exc_info=True)
            AGENT_REQUESTS.labels(outcome="crash", model_used="none", error_type="unhandled_graph_exception").inc()
            INVOKE_LATENCY.observe(time.perf_counter() - start)
            return {"response": "I'm sorry, I'm having trouble processing your request right now. Please try again in a moment.", "updated_session_summary": "", "model_used": "crash_handler", "error": "unhandled_graph_exception", "sources": [], "wants_human_handoff": False}

        INVOKE_LATENCY.observe(time.perf_counter() - start)
        model_used = result.get("model_used", "unknown")
        error = result.get("error")
        if error is None and model_used != "error_handler":
            outcome = "success" 
            SOURCES_PER_RESPONSE.labels(model_used=model_used).observe(len(result.get("sources") or []))
        else:
            outcome = "error"
        AGENT_REQUESTS.labels(outcome=outcome, model_used=model_used, error_type=(classify_error(Exception(error)) if error else "")).inc()
        return {"response": result["response"], "updated_session_summary": result["updated_session_summary"], "model_used": result.get("model_used", "unknown"), "error": result.get("error"), "sources": result.get("sources", []), "input_tokens": result.get("input_tokens", 0), "output_tokens": result.get("output_tokens", 0), "wants_human_handoff": result.get("wants_human_handoff", False), "best_distance": result.get("best_distance")}