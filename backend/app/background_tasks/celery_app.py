import ssl
from celery import Celery
from backend.app.config import get_settings


settings = get_settings()

celery_app = Celery("admiq", broker=settings.redis_url, backend=settings.redis_url, include=["backend.app.background_tasks.celery_tasks", "backend.app.background_tasks.student_profile_tasks", "backend.app.background_tasks.lead_scoring_tasks", "backend.app.background_tasks.reengagement_tasks"])

celery_app.conf.broker_use_ssl = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
celery_app.conf.redis_backend_use_ssl = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
celery_app.conf.beat_schedule = {"process_pending_tasks": {"task": "backend.app.background_tasks.student_profile_tasks.process_closed_sessions_task", "schedule": 300.0}, "recompute_lead_scores_nightly": {"task": "backend.app.background_tasks.lead_scoring_task", "schedule": 86400.0}, "check_reengagement_nudges": {"task": "backend.app.background_tasks.reengagement_tasks.check_and_send_reengagement_nudges_task", "schedule": 600.0}}