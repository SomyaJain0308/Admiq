import logging, json, time
from datetime import datetime, timezone

from prometheus_client import Counter, Histogram, CONTENT_TYPE_LATEST



# For observability used in agent.py.
REQUESTS_TOTAL = Counter("api_requests_total", "Total chat requests handled", ["model_used", "outcome"])

DOCUMENT_EXTRACTION_METHOD = Counter("document_extraction_method_total", "Document extraction tier method used", ["method"])

DOCUMENT_INGESTION_OUTCOME = Counter("document_ingestion_outcome_total", "Total document ingestion task outcomes", ["outcome", "error_type"])

CELERY_TASK_RETRIES = Counter("celery_task_retries_total", "Total celery task retries by task name and error type", ["task_name", "error_type"])

INPUT_TOKENS_TOTAL = Counter("api_input_tokens_total", "Total input tokens processed, for cost tracking", ["model_used"])

OUTPUT_TOKENS_TOTAL = Counter("api_output_tokens_total", "Total output tokens processed, for cost tracking", ["model_used"])

AGENT_REQUESTS = Counter("agent_requests_total", "Total agent invocations by final outcome, model used and error type (empty string on success)", ["outcome", "model_used", "error_type"])

AGENT_ERRORS = Counter("agent_error_total", "Total errors by stage and classified error type", ["stage", "error_type"])

AGENT_RETRIES = Counter("agent_retries_total", "Total retry attempts by stage", ["stage"])

LLM_INPUT_TOKENS = Counter("agent_llm_input_tokens", "Total input/prompt tokens consumed, for cost tracking", ["stage", "model_used"])

LLM_OUTPUT_TOKENS = Counter("agent_llm_output_tokens", "Total output/response tokens consumed, for cost tracking", ["stage", "model_used"])

STUDENT_TOKEN_BUDGET_REJECTIONS = Counter("agent_students_token_budget_rejections_total", "Total requests rejected because the requesting student's rolling token budget was exceeded")

AGENT_MISSING_FOLLOWUP = Counter("agent_missing_followup_total", "Total successful responses that didn't end with a question — rule 11 (always end with a follow-up) was not followed", ["model_used"])

DOCUMENT_INGESTION_LATENCY = Histogram("document_ingestion_latency_seconds", "End to end latency of document ingestion tasks (OCR + chunk + contextualize + embed + insert)")

DOCUMENT_INGESTION_STAGE_LATENCY = Histogram("document_ingestion_stage_latency_seconds", "Latency of each stage of document ingestion tasks (OCR + chunk + contextualize + embed + insert)", ["stage"])

DOCUMENT_QUALITY_SCORE = Histogram("document_quality_score", "Quality score ofextracted markdown (0-1, higher is better)", buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])

DOCUMENT_CHUNKS_CREATED = Histogram("documents_chunks_created", "Number of chunks created per successfully ingested document", buckets=[1, 5, 10, 20, 40, 80, 150, 300])

DOCUMENTS_PAGES_PROCESSED = Histogram("document_pages_processed", "Number of pages processed per successfully ingested document", buckets=[1, 3, 5, 10, 20, 40, 80])

REQUEST_LATENCY_MS = Histogram("api_request_latency_ms", "End-toend request latency in ms", ["model_used"])

STAGE_LATENCY = Histogram("agent_stage_latency_seconds", "Latency per llm call, labled by stage and model", ["stage", "model_used"])

RETRIEVAL_LATENCY = Histogram("agent_retrieval_latency", "Latency of the retrieval step")

INVOKE_LATENCY = Histogram("agent_invoke_latency_seconds", "End-to-end latency of a full agent invocation")

SOURCES_PER_RESPONSE = Histogram("agent_sources_per_response", "Number of sources cited per successful response (retrieval quality signal)", ["model_used"])

RETRIEVAL_DISTANCE = Histogram("agent_retrieval_chunk_distance", "Cosine distance of each retrieved chunk against the query — use this to tune retrieval_distance_threshold and min_relevant_chunks off real data", ["passed_threshold"], buckets=[0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.7, 0.85, 1.0])

QUERY_DECOMPOSITION_SIZE = Histogram("agent_query_decomposition_size", "Number of sub-queries split a student message into", buckets=[1, 2, 3, 4])

RETRIEVAL_ROUNDS_TO_RESOLVE = Histogram("agent_retrieval_rounds_to_resolve", "How many rounds (0 = resolved on first try) it took before all sub-queries were covered", buckets=[0, 1, 2, 3])

SUBQUERIES_UNRESOLVED = Histogram("agent_subqueries_unresolved_at_handoff", "Number of sub queries still unresolved when retries were exhausted and the turn was flagged low-confidence", buckets=[0, 1, 2, 3, 4])

METRICS_CONTENT_TYPE = CONTENT_TYPE_LATEST



class JSONFormatter(logging.Formatter):

    def format(self, record):
        log_obj = {"timestamp": datetime.now(timezone.utc).isoformat(), "level": record.levelname, "message": record.getMessage(), "module": record.module, "funtion": record.funcName}
        extra_data = getattr(record, "extra_data", None)
        if extra_data:
            log_obj.update(extra_data)
        return json.dumps(log_obj)
    

def get_logger(name: str = "production-api") -> logging.Logger: # Adding permanent comments since I keep forgetting this block of very cryptic code
    logger = logging.getLogger(name)             # Check if we alr have a logger (postoffice)
    if not logger.handlers:                      # Check if we alr have a log handler (postman)
        handler = logging.StreamHandler()        # Assign a handler (postman) if not available alr
        handler.setFormatter(JSONFormatter())    # Pack the log (package) from plain text to json
        logger.addHandler(handler)               # Connect the log and the handler
        logger.setLevel(logging.INFO)            # Only process messages that are info, warning or error level
    return logger


class RequestTimer():
    def __enter__(self):
        self.start = time.time()
        return self
    
    def __exit__(self, *args):
        self.elapsed_ms = (time.time() - self.start) * 1000