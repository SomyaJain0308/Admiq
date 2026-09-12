from prometheus_client import Counter, Histogram, Gauge



REQUESTS_TOTAL = Counter("api_requests_total", "Total Chat Requests Handled", ["model_used", "outcome"])

REQUEST_LATENCY_MS = Histogram("api_request_latency_ms", "End-to-End Request Latency in ms", ["model_used"])

WHATSAPP_SEND_OUTCOMES = Counter("whatsapp_send_outcomes_total", "Outbound Whatsapp mesage send attempts by outcoms", ["outcome"])

WHATSAPP_SEND_LATENCY_SECONDS = Histogram("whatsapp_send_latency_seconds", "Latency of the outbound WhatsApp API call itself, isolated from agent/DB latency")

DUPLICATE_WEBHOOK_DELIVERY = Counter("api_duplicate_webhook_deliveries_total", "Total Meta Webhook redeliveries skipped as duplicate")

OUTPUT_SECURITY_WARNINGS = Counter("api_output_security_warnings_total", "Total responses flagged by the output security filter before sending")

STUDENT_TOKEN_BUDGET_REJECTIONS = Counter("agent_students_token_budget_rejections_total", "Total requests rejected because the requesting student's rolling token budget was exceeded")

from prometheus_client import Gauge

# --- Security signals that were being detected but never counted ---

INPUT_SECURITY_BLOCKS = Counter("api_input_security_blocks_total", "Total inbound messages blocked by the input sanitizer", ["channel", "reason"])

WEBHOOK_SIGNATURE_INVALID = Counter("whatsapp_webhook_signature_invalid_total", "Total webhook deliveries rejected for a bad/missing Meta signature")

RATE_LIMIT_REJECTIONS = Counter("api_rate_limit_rejections_total", "Total requests rejected by the rate limiter", ["route"])

STAFF_LOGIN_OUTCOMES = Counter("staff_login_outcomes_total", "Staff login attempts by outcome", ["outcome"])  # success / invalid_credentials / deactivated

# --- App-wide HTTP visibility (generic ASGI middleware, see monitoring/http_metrics_middleware.py) ---

HTTP_REQUESTS_TOTAL = Counter("http_requests_total", "Total HTTP requests", ["method", "route", "status_code"])

HTTP_REQUEST_DURATION = Histogram("http_request_duration_seconds", "HTTP request latency", ["method", "route"])

# --- Dependency health ---

DB_QUERY_ERRORS = Counter("db_query_errors_total", "Database errors by operation", ["operation", "error_type"])

REDIS_ERRORS = Counter("redis_errors_total", "Redis errors", ["operation"])

# --- Business/product gauges, updated periodically by a Celery beat task ---

ACTIVE_STUDENTS_7D = Gauge("students_active_7d", "Distinct students with a message in the last 7 days", ["college_id"])

DOCUMENTS_INDEXED = Gauge("documents_indexed_total", "Currently indexed documents", ["college_id"])