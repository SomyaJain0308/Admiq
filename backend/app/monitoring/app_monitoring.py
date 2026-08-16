from prometheus_client import Counter, Gauge, Histogram, CONTENT_TYPE_LATEST



REQUEST_COUNT = Counter("app_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])

REQUEST_LATENCY = Histogram("app_request_latency_seconds", "Request latency in seconds", ["endpoint"], buckets=[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10])

ACTIVE_USERS = Gauge("app_active_users", "Currently active users")

METRICS_CONTENT_TYPE = CONTENT_TYPE_LATEST