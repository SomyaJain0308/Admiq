import ssl
from celery import Celery
from backend.app.config import get_settings


settings = get_settings()

celery_app = Celery("admiq", broker=settings.redis_url, backend=settings.redis_url, include=["backend.backgroundTasks.celery_tasks"])

celery_app.conf.broker_use_ssl = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
celery_app.conf.redis_backend_use_ssl = {"ssl_cert_reqs": ssl.CERT_REQUIRED}