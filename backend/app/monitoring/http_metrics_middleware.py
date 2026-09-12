"""
Generic ASGI middleware that instruments every HTTP route in the app, not
just the chat endpoint (which api_metrics.REQUESTS_TOTAL/REQUEST_LATENCY_MS
already cover). Everything else - colleges, staff CRUD, students, documents,
dashboard, costs, health - was previously dark: no request counts, no
latency, no status-code breakdown, so a deploy that broke e.g. the
documents router would only show up as user reports, not a metric.

Implemented as a plain ASGI middleware (not BaseHTTPMiddleware) so it works
transparently with streaming responses and doesn't buffer the body.

Route label: Starlette sets scope["route"] once routing has matched a
request, and that mutation is visible to us because scope is the same dict
threaded through the whole ASGI chain. Using route.path (the path template,
e.g. "/router/staff/{college_id}/{staff_id}") instead of the raw request
path keeps cardinality bounded - a raw path would create a new label series
per college_id/staff_id ever seen. Requests that don't match any route
(404s) fall back to a fixed "unmatched" label for the same reason.
"""

import time

from backend.app.monitoring.api_metrics import HTTP_REQUESTS_TOTAL, HTTP_REQUEST_DURATION


class HTTPMetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "UNKNOWN")
        status_code = 500  # Assume the worst until a response actually starts; an unhandled exception never sends a status.
        start = time.perf_counter()

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = scope.get("route")
            route_label = route.path if route is not None else "unmatched"
            duration = time.perf_counter() - start
            HTTP_REQUESTS_TOTAL.labels(method=method, route=route_label, status_code=str(status_code)).inc()
            HTTP_REQUEST_DURATION.labels(method=method, route=route_label).observe(duration)
