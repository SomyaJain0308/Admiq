from prometheus_client import Counter, Histogram




BACKGROUND_TASK_ITEM_OUTCOMES = Counter("background_task_item_outcomes_total", "Per-item outcome (one increment per session/student processed within a batch)", ["task_name", "outcome"])

BACKGROUND_TASK_BATCH_DURATION = Counter("background_task_batch_duration_seconds", "Duration of one full task run, start to finish", ["task_name"])

BACKGROUND_TASK_BATCH_SIZE = Histogram("background_task_batch_size", "Number of candidate rows pulled in one batch, before per item processing", ["task_name"], buckets=[0, 1, 5, 10, 25, 50, 100, 200])


REENGAGEMENT_CANDIDATE_OUTCOMES = Counter("reengagement_candidates_outcomes_total", "Why each reengagement candidate did or didn't get a nudge sent", ["outcome"])


LEAD_SCORE_DISTRIBUTION = Histogram("lead_score_distribution", "Distribution of compute lead scores (0-100)", ["source"], buckets=[10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
