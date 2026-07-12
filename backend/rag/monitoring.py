import logging
import json
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable

# The sole purpose of this file is logging

class JSONFormatter(logging.Formatter):

    def format(self, record):
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "funtion": record.funcName,
        }

        if hasattr(record, "extra_data"):
            log_obj.update(record.extra_data)
        return json.dumps(log_obj)
    

def get_logger(name: str = "production-api") -> logging.Logger:
    logger = logging.getLogger(name) # Check if we alr have a logger (postoffice)
    if not logger.handlers: # Check if we alr have a log handler (postman)
        handler = logging.StreamHandler() # Assign a handler (postman) if not available alr
        handler.setFormatter(JSONFormatter()) # Pack the log (package) from plain text to json
        logger.addHandler(handler) # Connect the log and the handler
        logger.setLevel(logging.INFO) # Only process messages that are info, warning or error level
    return logger

class MetricsCollector: # Collects and aggregates application metrics IN PRODUCTION REPLACE WITH PROMETHEUS CLIENT
    def __init__(self):
        self._requests_total = 0
        self._errors_total = 0
        self._latency_sum = 0.0
        self._latency_count = 0
        self._tokens_input = 0
        self._tokens_output = 0
        self._cache_hits = 0
        self._cache_misses = 0

    def record_request(
            self,
            latency_ms: float,
            input_tokens: int = 0,
            output_tokens: int = 0,
            error: bool = False,
            cache_hit: bool = False,
    ):
        self._requests_total += 1
        self._latency_sum +=latency_ms
        self._latency_count += 1 
        self._tokens_input += input_tokens
        self._tokens_output += output_tokens
        if error:
            self._errors_total += 1
        if cache_hit:
            self._cache_hits += 1
        else:
            self._cache_misses += 1
    

    @property
    def summary(self) -> dict:
        avg_latency = (
            self._latency_sum / self._latency_count
            if self._requests_total > 0 else 0.0
            )
        error_rate = (
            self._errors_total / self._requests_total
            if self._requests_total > 0 else 0.0
        )
        cache_total = self._cache_hits + self._cache_misses
        cache_hit_rate = (
            self._cache_hits / cache_total
            if cache_total > 0 else 0.0
        )
        return {
            "total_requests": self._requests_total,
            "total_errors": self._errors_total,
            "error_rate": f"{error_rate:.2%}",
            "avg_latency_ms": round(avg_latency, 2),
            "cache_hit_rate": f"{cache_hit_rate:.2%}",
            "total_input_tokens": self._tokens_input,
            "total_output_tokens": self._tokens_output,
        }
    

class RequestTimer: # Context Manager for timing requests
    def __enter__(self):
        self.start = time.time()
        return self
    
    def __exit__(self, *args):
        self.elapsed_ms = (time.time() - self.start) * 1000