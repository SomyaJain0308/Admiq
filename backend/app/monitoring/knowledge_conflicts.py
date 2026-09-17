from prometheus_client import Counter, Gauge


KNOWLEDGE_CONFLICTS_FLAGGED = Counter("knowledge_conflicts_flagged_total", "Total conflicts flagged between a new/edited chunk and an existing one", ["source_type"])

KNOWLEDGE_CONFLICTS_REVIEWED = Counter("knowledge_conflicts_reviewed_total", "Total conflicts reviewed by staff", ["outcome"])  # outcome: resolved | dismissed

KNOWLEDGE_CONFLICTS_OPEN = Gauge("knowledge_conflicts_open", "Current number of unreviewed conflicts waiting on staff")
