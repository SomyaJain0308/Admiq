from prometheus_client import Counter


CELERY_TASK_RETRIES = Counter("celery_task_retries_total", "Total celery task retries by task name and error type", ["task_name", "error_type"])