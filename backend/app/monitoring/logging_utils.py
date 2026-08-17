import logging, json, time
from datetime import datetime, timezone


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