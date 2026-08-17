from prometheus_client import Counter, Histogram 



AGENT_REQUESTS = Counter("agent_requests_total", "Total agent invocations by final outcome, model used and error type (empty string on success)", ["outcome", "model_used", "error_type"])



NEEDS_RETRIEVAL_COUNT = Counter("agent_query_needs_retrieval", "Number of queries that needed retrieval")

QUERY_DECOMPOSITION_SIZE = Histogram("agent_query_decomposition_size", "Number of sub-queries split a student message into", buckets=[1, 2, 3, 4])



RETRIEVED_CHUNKS_COUNT = Histogram("agent_retrieved_chunks_count", "Number of all retrieved chunks")

RETRIEVAL_DISTANCE = Histogram("agent_retrieval_chunk_distance", "Cosine distance of each retrieved chunk against the query - use this to tune retrieval_distance_threshold and min_relevant_chunks off real data", ["passed_threshold"], buckets=[0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])

RELEVANT_CHUNKS_COUNT = Histogram("agent_relevant_chunks_count", "Number of relevant chunks out of all retrieved")



SUBQUERIES_UNRESOLVED = Histogram("agent_subqueries_unresolved_at_handoff", "Number of sub queries still unresolved when retries were exhausted and the turn was flagged low-confidence", buckets=[0, 1, 2, 3, 4])



INVOKE_LATENCY = Histogram("agent_invoke_latency_seconds", "End-to-end latency of a full agent invocation")



LLM_INPUT_TOKENS = Counter("agent_llm_input_tokens", "Total input/prompt tokens consumed, for cost tracking", ["stage", "model_used"])

LLM_OUTPUT_TOKENS = Counter("agent_llm_output_tokens", "Total output/response tokens consumed, for cost tracking", ["stage", "model_used"])

AGENT_MISSING_FOLLOWUP = Counter("agent_missing_followup_total", "Total per llm call, labeled by stage and model", ["stage", "model_used"])

AGENT_ERRORS = Counter("agent_error_total", "Total errors by stage and classified error type", ["stage", "error_type"])

AGENT_RETRIES = Counter("agent_retries_total", "Total retry attempts by stage", ["stage"])

STAGE_LATENCY = Histogram("agent_stage_latency_seconds", "Latency per llm call, labeled by stage and llm", ["stage", "model_used"])