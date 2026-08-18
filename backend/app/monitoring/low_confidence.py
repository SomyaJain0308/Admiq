from prometheus_client import Counter, Gauge, Histogram




LOW_CONFIDENCE_QUERIES_FLAGGED = Counter("low_confidence_queries_flagged_total", "Total queries flagged for human staff handoff")


LOW_CONFIDENCE_QUERIES_RESOLVED = Counter("low_confidence_queries_resolved_total", "Total flagged queries resolved by staff")


LOW_CONFIDENCE_RESOLUTION_TIME_SECONDS = Histogram("low_confidence_resolution_time_seconds", "Time between a query being flagged and staff resolving it", buckets=[300, 900, 1800, 3600, 7200, 14400, 28800, 86400, 172800, 259200])


LOW_CONFIDENCE_QUERIES_OPEN = Gauge("low_confidence_queries_open", "Current number of unresolved queries waiting on staff")