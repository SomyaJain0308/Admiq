from prometheus_client import Counter, Histogram



REQUESTS_TOTAL = Counter("api_requests_total", "Total Chat Requests Handled", ["model_used", "outcome"])

REQUEST_LATENCY_MS = Histogram("api_request_latency_ms", "End-to-End Request Latency in ms", ["model_used"])

WHATSAPP_SEND_FAILURES = Counter("api_whatsapp_send_failures_total", "Total failed outbound WhatsApp API send attempts")

DUPLICATE_WEBHOOK_DELIVERY = Counter("api_duplicate_webhook_deliveries_total", "Total Meta Webhook redeliveries skipped as duplicate")

OUTPUT_SECURITY_WARNINGS = Counter("api_output_security_warnings_total", "Total responses flagged by the output security filter before sending")

STUDENT_TOKEN_BUDGET_REJECTIONS = Counter("agent_students_token_budget_rejections_total", "Total requests rejected because the requesting student's rolling token budget was exceeded")