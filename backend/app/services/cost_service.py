"""
Turns token counts / WhatsApp sends into dollar amounts and persists them to
the cost_events table (see backend/app/models/CostEvent.py and
backend/app/schema.sql) so per-student and per-college cost can be
aggregated afterwards - total, average, median, p95, whatever's needed -
via SQL rather than only living as Prometheus counters.

Pricing tables below are point-in-time defaults (checked Sep 2026). Verify
against https://ai.google.dev/gemini-api/docs/pricing periodically - Google
revises these, and an unpriced model silently costs $0 here rather than
raising, so it's easy to miss a stale or missing entry. If you add a new
primary/fallback/query/embedding model in Settings, add a matching entry
here too.
"""

import logging

from backend.app.config import get_settings
from backend.app.models.CostEvent import CostEvent

logger = logging.getLogger(__name__)

# $ per 1,000,000 tokens, standard (non-batch) tier.
LLM_PRICING_PER_MILLION_TOKENS = {
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
}

# $ per 1,000,000 input tokens. Gemini embedding models have no billable
# output tokens (the response is a fixed-size vector).
EMBEDDING_PRICING_PER_MILLION_TOKENS = {
    "models/gemini-embedding-001": {"input": 0.15},
    "gemini-embedding-001": {"input": 0.15},
}

# Rough fallback for estimating embedding token counts from raw text, since
# the LangChain embeddings wrapper used in rag/retrieval.py and rag/chunking.py
# doesn't surface actual token usage the way the chat models do. ~4 chars/
# token is the standard rule-of-thumb approximation for English text - good
# enough for a cost estimate, not exact.
CHARS_PER_TOKEN_ESTIMATE = 4


def estimate_tokens_from_text(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN_ESTIMATE)


def compute_llm_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = LLM_PRICING_PER_MILLION_TOKENS.get(model)
    if pricing is None:
        logger.warning("No pricing entry for LLM model=%s - cost will be recorded as $0. Add it to cost_service.LLM_PRICING_PER_MILLION_TOKENS.", model)
        return 0.0
    return (input_tokens / 1_000_000) * pricing["input"] + (output_tokens / 1_000_000) * pricing["output"]


def compute_embedding_cost_usd(model: str, input_tokens: int) -> float:
    pricing = EMBEDDING_PRICING_PER_MILLION_TOKENS.get(model)
    if pricing is None:
        logger.warning("No pricing entry for embedding model=%s - cost will be recorded as $0. Add it to cost_service.EMBEDDING_PRICING_PER_MILLION_TOKENS.", model)
        return 0.0
    return (input_tokens / 1_000_000) * pricing["input"]


def whatsapp_conversation_cost_usd(category: str) -> float:
    settings = get_settings()
    return {
        "session": settings.whatsapp_session_message_cost_usd,
        "utility": settings.whatsapp_utility_conversation_cost_usd,
        "marketing": settings.whatsapp_marketing_conversation_cost_usd,
    }.get(category, 0.0)


async def record_llm_cost(db, *, college_id: int, student_id: int | None, session_id: int | None, stage: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """Async variant - call from request-handling code (agent.py nodes) that
    already holds an AsyncSession. Commits its own row, matching how every
    other service function in this codebase (session_service.py,
    tenant_service.py) commits immediately rather than batching."""
    settings = get_settings()
    if not settings.llm_cost_tracking_enabled or (input_tokens <= 0 and output_tokens <= 0):
        return 0.0
    cost_usd = compute_llm_cost_usd(model, input_tokens, output_tokens)
    db.add(CostEvent(college_id=college_id, student_id=student_id, session_id=session_id, cost_type="llm", stage=stage, model=model, input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost_usd))
    await db.commit()
    return cost_usd


async def record_embedding_cost(db, *, college_id: int, student_id: int | None, session_id: int | None, stage: str, model: str, input_tokens: int) -> float:
    settings = get_settings()
    if not settings.llm_cost_tracking_enabled or input_tokens <= 0:
        return 0.0
    cost_usd = compute_embedding_cost_usd(model, input_tokens)
    db.add(CostEvent(college_id=college_id, student_id=student_id, session_id=session_id, cost_type="embedding", stage=stage, model=model, input_tokens=input_tokens, output_tokens=0, cost_usd=cost_usd))
    await db.commit()
    return cost_usd


def record_embedding_cost_sync(db, *, college_id: int, document_id: int | None, model: str, input_tokens: int) -> float:
    """Sync variant for document ingestion (rag/chunking.py's
    insert_chunks_to_db), which runs on the sync SessionLocal, not the async
    session used everywhere else. student_id/session_id are omitted - a
    document's embedding cost isn't attributable to one student, it's a
    college-level knowledge-base overhead cost."""
    settings = get_settings()
    if not settings.llm_cost_tracking_enabled or input_tokens <= 0:
        return 0.0
    cost_usd = compute_embedding_cost_usd(model, input_tokens)
    db.add(CostEvent(college_id=college_id, student_id=None, session_id=None, document_id=document_id, cost_type="embedding", stage="document_ingestion", model=model, input_tokens=input_tokens, output_tokens=0, cost_usd=cost_usd))
    db.commit()
    return cost_usd


async def record_whatsapp_cost(db, *, college_id: int, student_id: int | None, session_id: int | None, category: str, success: bool) -> float:
    """category is 'session' for a free-form reply inside the 24h customer
    service window, or 'utility'/'marketing' for a template-triggered send
    outside it (staff-initiated follow-up, reengagement nudge). Only
    successful sends are billed - Meta doesn't charge for a rejected send."""
    settings = get_settings()
    if not settings.llm_cost_tracking_enabled or not success:
        return 0.0
    cost_usd = whatsapp_conversation_cost_usd(category)
    db.add(CostEvent(college_id=college_id, student_id=student_id, session_id=session_id, cost_type="whatsapp", stage=f"whatsapp_{category}", model=None, input_tokens=0, output_tokens=0, cost_usd=cost_usd))
    await db.commit()
    return cost_usd
