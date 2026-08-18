from prometheus_client import Counter, Histogram



REQUESTS_TOTAL = Counter("api_requests_total", "Total Chat Requests Handled", ["model_used", "outcome"])

REQUEST_LATENCY_MS = Histogram("api_request_latency_ms", "End-to-End Request Latency in ms", ["model_used"])

WHATSPAP_SEND_OUTCOMES = Counter("whatsapp_send_outcomes_total", "Outbound Whatsapp mesage send attempts by outcoms", ["outcome"])

WHATSAPP_SEND_LATENCY_SECONDS = Histogram("whatsapp_send_latency_seconds", "Latency of the outbound WhatsApp API call itself, isolated from agent/DB latency")

DUPLICATE_WEBHOOK_DELIVERY = Counter("api_duplicate_webhook_deliveries_total", "Total Meta Webhook redeliveries skipped as duplicate")

OUTPUT_SECURITY_WARNINGS = Counter("api_output_security_warnings_total", "Total responses flagged by the output security filter before sending")

STUDENT_TOKEN_BUDGET_REJECTIONS = Counter("agent_students_token_budget_rejections_total", "Total requests rejected because the requesting student's rolling token budget was exceeded")