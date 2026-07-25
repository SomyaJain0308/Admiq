import logging
import json
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# The sole purpose of this file is logging

class JSONFormatter(logging.Formatter):

    def format(self, record):
        log_obj = {"timestamp": datetime.now(timezone.utc).isoformat(), "level": record.levelname, "message": record.getMessage(), "module": record.module, "funtion": record.funcName}
        if hasattr(record, "extra_data"):
            log_obj.update(record.extra_data)
        return json.dumps(log_obj)
    

def get_logger(name: str = "production-api") -> logging.Logger: # Adding permanent comments since I keep forgetting this cryptic code
    logger = logging.getLogger(name) # Check if we alr have a logger (postoffice)
    if not logger.handlers: # Check if we alr have a log handler (postman)
        handler = logging.StreamHandler() # Assign a handler (postman) if not available alr
        handler.setFormatter(JSONFormatter()) # Pack the log (package) from plain text to json
        logger.addHandler(handler) # Connect the log and the handler
        logger.setLevel(logging.INFO) # Only process messages that are info, warning or error level
    return logger


REQUESTS_TOTAL = Counter("api_requests_total", "Total chat requests handled", ["model_used", "outcome"])

INPUT_TOKENS_TOTAL = Counter("api_input_tokens_total", "Total input tokens processed, for cost tracking", ["model_used"])

OUTPUT_TOKENS_TOTAL = Counter("api_output_tokens_total", "Total output tokens processed, for cost tracking", ["model_used"])

AGENT_REQUESTS = Counter("agent_requests_total", "Total agent invocations by final outcome, model used and error type (empty string on success)", ["outcome", "model_used", "error_type"])

AGENT_ERRORS = Counter("agent_error_total", "Total errors by stage and classified error type", ["stage", "error_type"])

AGENT_RETRIES = Counter("agent_retries_total", "Total retry attempts by stage", ["stage"])

LLM_INPUT_TOKENS = Counter("agent_llm_input_tokens", "Total input/prompt tokens consumed, for cost tracking", ["stage", "model_used"])

LLM_OUTPUT_TOKENS = Counter("agent_llm_output_tokens", "Total output/response tokens consumed, for cost tracking", ["stage", "model_used"])

STUDENT_TOKEN_BUDGET_REJECTIONS = Counter("agent_students_token_budget_rejections_total", "Total requests rejected because the requesting student's rolling token budget was exceeded")

AGENT_MISSING_FOLLOWUP = Counter("agent_missing_followup_total", "Total successful responses that didn't end with a question — rule 11 (always end with a follow-up) was not followed", ["model_used"])

REQUEST_LATENCY_MS = Histogram("api_request_latency_ms", "End-toend request latency in ms", ["model_used"])

STAGE_LATENCY = Histogram("agent_stage_latency_seconds", "Latency per llm call, labled by stage and model", ["stage", "model_used"])

RETRIEVAL_LATENCY = Histogram("agent_retrieval_latency", "Latency of the retrieval step")

INVOKE_LATENCY = Histogram("agent_invoke_latency_seconds", "End-to-end latency of a full agent invocation")

SOURCES_PER_RESPONSE = Histogram("agent_sources_per_response", "Number of sources cited per successful response (retrieval quality signal)", ["model_used"])

RETRIEVAL_DISTANCE = Histogram("agent_retrieval_chunk_distance", "Cosine distance of each retrieved chunk against the query — use this to tune retrieval_distance_threshold and min_relevant_chunks off real data", ["passed_threshold"], buckets=[0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.7, 0.85, 1.0])

METRICS_CONTENT_TYPE = CONTENT_TYPE_LATEST

def get_metrics_text() -> bytes:
    return generate_latest()



class MetricsCollector: # Collects and aggregates application metrics
    def __init__(self):
        self._requests_total = 0
        self._errors_total = 0
        self._latency_sum = 0.0
        self._latency_count = 0
        self._tokens_input = 0
        self._tokens_output = 0

    def record_request(self, latency_ms: float, input_tokens: int = 0, output_tokens: int = 0, error: bool = False, model_used: str = "unknown"):
        self._requests_total += 1
        self._latency_sum += latency_ms
        self._latency_count += 1 
        self._tokens_input += input_tokens
        self._tokens_output += output_tokens
        if error:
            self._errors_total += 1
            outcome = "error"
        else:
            outcome = "success"

        REQUESTS_TOTAL.labels(model_used=model_used, outcome=outcome).inc()
        REQUEST_LATENCY_MS.labels(model_used=model_used).observe(latency_ms)
        if input_tokens:
            INPUT_TOKENS_TOTAL.labels(model_used=model_used).inc(input_tokens)
        if output_tokens:
            OUTPUT_TOKENS_TOTAL.labels(model_used=model_used).inc(output_tokens)
    

    @property
    def summary(self) -> dict:
        if self._requests_total > 0:
            avg_latency = self._latency_sum / self._latency_count
            error_rate = self._errors_total / self._requests_total
        else:
            avg_latency = 0.0
            error_rate = 0.0
        
        return {
            "total_requests": self._requests_total,
            "total_errors": self._errors_total,
            "error_rate": f"{error_rate:.2%}",
            "avg_latency_ms": round(avg_latency, 2),
            "total_input_tokens": self._tokens_input,
            "total_output_tokens": self._tokens_output,
        }
    

class RequestTimer: # Context Manager for timing requests
    def __enter__(self):
        self.start = time.time()
        return self
    
    def __exit__(self, *args):
        self.elapsed_ms = (time.time() - self.start) * 1000
