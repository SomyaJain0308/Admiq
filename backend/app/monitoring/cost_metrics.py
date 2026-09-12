from prometheus_client import Gauge

# --- Internal $ cost gauges ---
#
# Deliberately NOT served through backend/app/api/v1/routers/costs.py's
# token-gated REST endpoint - that endpoint is untouched and stays
# unreachable by any college-staff JWT, by construction, per its own
# module docstring.
#
# These gauges are a second, independent pipe to the same underlying
# cost_events table: background_tasks/cost_metrics_tasks.py recomputes
# them on a schedule (see celery_app.py beat_schedule) and sets them here,
# following the exact same snapshot-gauge pattern as ACTIVE_STUDENTS_7D /
# DOCUMENTS_INDEXED in api_metrics.py. They only ever reach Prometheus/
# Grafana - nothing in the frontend reads them, so the isolation the costs
# router is built around still holds; this just gives *you* a live view.

COST_USD_ALL_TIME = Gauge("cost_usd_all_time", "Total recorded cost in USD, all time", ["college_id"])

COST_USD_LAST_7D = Gauge("cost_usd_last_7d", "Total recorded cost in USD, trailing 7 days", ["college_id"])

COST_USD_BY_TYPE_LAST_7D = Gauge("cost_usd_by_type_last_7d", "Cost in USD by cost_type (llm/embedding/whatsapp), trailing 7 days", ["college_id", "cost_type"])
