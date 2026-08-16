INTEREST_SIGNAL_VALUES = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}

INTEREST_WEIGHT = 45
RECENCY_WEIGHT = 35
FREQUENCY_WEIGHT = 20

RECENCY_FULL_CREDIT_DAYS = 1
RECENCY_ZERO_CREDIT_DAYS = 30

FREQUENCY_SESSIONS_FOR_FULL_CREDIT = 5

CONCERN_PENALTY = 4
CONCERN_PENALTY_CAP = 15
COMPETING_COLLEGE_PENALTY = 4
COMPETING_COLLEGE_PENALTY_CAP = 15
DROPOFF_PENALTY = 10


def _interest_component(interest_signal_history: list[str] | None) -> float:
    history = [s for s in (interest_signal_history or []) if s in INTEREST_SIGNAL_VALUES]
    if not history:
        return INTEREST_WEIGHT * 0.5
    weights = list(range(1, len(history) + 1))
    weighted_sum = sum(INTEREST_SIGNAL_VALUES[s] * w for s, w in zip(history, weights))
    total_weight = sum(weights)
    avg = weighted_sum / total_weight
    normalized = (avg + 1) / 2
    return normalized * INTEREST_WEIGHT


def _recency_component(days_since_last_activity: float | None) -> float:
    if days_since_last_activity is None:
        return 0.0
    if days_since_last_activity <= RECENCY_FULL_CREDIT_DAYS:
        return RECENCY_WEIGHT
    if days_since_last_activity >= RECENCY_ZERO_CREDIT_DAYS:
        return 0.0
    span = RECENCY_ZERO_CREDIT_DAYS - RECENCY_FULL_CREDIT_DAYS
    remaining = RECENCY_ZERO_CREDIT_DAYS - days_since_last_activity
    return RECENCY_WEIGHT * (remaining / span)


def _frequency_component(total_sessions: int) -> float:
    if total_sessions <= 0:
        return 0.0
    fraction = min(total_sessions, FREQUENCY_SESSIONS_FOR_FULL_CREDIT) / FREQUENCY_SESSIONS_FOR_FULL_CREDIT
    return FREQUENCY_WEIGHT * fraction


def compute_lead_score(interest_signal_history: list[str] | None, days_since_last_activity: float | None, total_sessions: int, concerns: list[str] | None = None, competing_colleges: list[str] | None = None, dropoff_reason: str | None = None) -> int:
    base_score = (_interest_component(interest_signal_history) + _recency_component(days_since_last_activity) + _frequency_component(total_sessions))
    concern_penalty = min(len(concerns or []) * CONCERN_PENALTY, CONCERN_PENALTY_CAP)
    competing_penalty = min(len(competing_colleges or []) * COMPETING_COLLEGE_PENALTY, COMPETING_COLLEGE_PENALTY_CAP)
    dropoff_penalty = DROPOFF_PENALTY if dropoff_reason else 0
    total_penalty = concern_penalty + competing_penalty + dropoff_penalty
    score = base_score - total_penalty
    return max(0, min(100, round(score)))