import logging, json, time
from datetime import datetime, timezone
from typing import Any, MutableMapping

from backend.app.config import get_settings


class JSONFormatter(logging.Formatter):

    def format(self, record):
        log_obj = {"timestamp": datetime.now(timezone.utc).isoformat(), "level": record.levelname, "message": record.getMessage(), "module": record.module, "funtion": record.funcName}
        extra_data = getattr(record, "extra_data", None)
        if extra_data:
            log_obj.update(extra_data)
        return json.dumps(log_obj)



def _resolve_log_level(level_str: str) -> int:
    level = getattr(logging, level_str.upper(), None)
    return level if isinstance(level, int) else logging.INFO



def get_logger(name: str = "production-api") -> logging.Logger: # Adding permanent comments since I keep forgetting this block of very cryptic code
    logger = logging.getLogger(name)             # Check if we alr have a logger (postoffice)
    if not logger.handlers:                      # Check if we alr have a log handler (postman)
        handler = logging.StreamHandler()        # Assign a handler (postman) if not available alr
        handler.setFormatter(JSONFormatter())    # Pack the log (package) from plain text to json
        logger.addHandler(handler)               # Connect the log and the handler
        logger.setLevel(_resolve_log_level(get_settings().log_level))            # Only process messages that are info, warning or error level
    return logger



class ContextLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.get("extra", {})
        call_extra_data = extra.get("extra_data", {})
        merged = {**(self.extra or {}), **call_extra_data}
        kwargs["extra"] = {"extra_data": merged}
        return msg, kwargs