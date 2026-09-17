"""Flags when a chunk that's about to enter (or was just edited in) the
knowledge base states a different, incompatible fact than something already
there. Runs best-effort from three call sites, all after the triggering
write has already happened (or been flushed) so a flaky LLM/embedding call
here can never block or fail the write itself:

  - backend/app/background_tasks/celery_tasks.py (sync) - a document's new
    chunks, after insert_chunks_to_db.
  - backend/app/api/v1/routers/low_confidence.py (async) - a reactive staff
    reply, right after its chunk is added/flushed.
  - backend/app/api/v1/routers/knowledge_base.py (async) - a proactive
    knowledge-base entry being created or edited.

Two-stage, matching the shape of rag/chunking.py's contextualization pass:
first a cheap vector search narrows to existing chunks close enough in
meaning to plausibly be about the same fact, then one batched LLM call
judges which of those (if any) actually contradict the new content. Nothing
here ever blocks or rolls back the caller's write - every stage swallows its
own exceptions and returns an empty result on failure.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.models.Chunk import Chunk
from backend.app.models.KnowledgeConflict import KnowledgeConflict
from backend.app.services.cost_service import record_llm_cost, record_llm_cost_sync
from backend.app.monitoring.knowledge_conflicts import KNOWLEDGE_CONFLICTS_FLAGGED

logger = logging.getLogger(__name__)

CONFLICT_DETECTION_STAGE = "conflict_detection"

CONFLICT_SYSTEM_INSTRUCTION = "You are auditing a college admissions knowledge base for factual contradictions before new content is saved."


class ConflictFinding(BaseModel):
    candidate_index: int = Field(description='Index of the candidate this finding is about, matching its <candidate index="..."> tag.')
    conflicts: bool = Field(description="True only if the candidate states a different, incompatible value for the same specific fact as the new content.")
    explanation: str = Field(description="If conflicts is true: 1-2 sentences naming what the new content says, what the candidate says, and why they can't both be true. Empty string if conflicts is false.")


class ConflictJudgement(BaseModel):
    findings: List[ConflictFinding] = Field(description="One finding per candidate, in the same order as the candidate indices.")


def _build_conflict_prompt(new_text: str, candidate_texts: List[str]) -> str:
    candidates_block = "\n\n".join(f'<candidate index="{i}">\n{text}\n</candidate>' for i, text in enumerate(candidate_texts))
    return (
        "New content about to be added to the knowledge base:\n"
        f"<new>\n{new_text}\n</new>\n\n"
        "Existing knowledge-base entries that are semantically close to it:\n"
        f"{candidates_block}\n\n"
        "For each candidate, decide whether it factually CONTRADICTS the new content - i.e. they give "
        "different, incompatible values for the same specific fact (the same course/programme/category/policy's "
        "fee, deadline, eligibility cutoff, seat count, process step, contact detail, etc). Do NOT flag a "
        "candidate just because it covers a related topic, adds extra detail, talks about a different "
        "course/programme/category, or could simply be an older answer to the same general question without "
        "actually stating a different value.\n\n"
        "Return exactly one finding per candidate, in the same order as the candidate indices."
    )


def _find_candidates_sync(db: Session, college_id: int, new_chunk: Chunk, k: int, distance_threshold: float) -> list[tuple[Chunk, float]]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stmt = (
        select(Chunk, Chunk.embedding.cosine_distance(new_chunk.embedding).label("distance"))
        .where(Chunk.college_id == college_id, Chunk.chunk_id != new_chunk.chunk_id, or_(Chunk.expires_at.is_(None), Chunk.expires_at > now))
    )
    if new_chunk.source_type == "document" and new_chunk.document_id is not None:
        # Other chunks of the SAME document aren't a meaningful "conflict" -
        # they're just neighbouring sections of one source.
        stmt = stmt.where(or_(Chunk.document_id.is_(None), Chunk.document_id != new_chunk.document_id))
    stmt = stmt.order_by("distance").limit(k)
    rows = db.execute(stmt).all()
    return [(c, float(d)) for c, d in rows if d is not None and float(d) <= distance_threshold]


async def _find_candidates_async(db: AsyncSession, college_id: int, new_chunk: Chunk, k: int, distance_threshold: float) -> list[tuple[Chunk, float]]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stmt = (
        select(Chunk, Chunk.embedding.cosine_distance(new_chunk.embedding).label("distance"))
        .where(Chunk.college_id == college_id, Chunk.chunk_id != new_chunk.chunk_id, or_(Chunk.expires_at.is_(None), Chunk.expires_at > now))
    )
    if new_chunk.source_type == "document" and new_chunk.document_id is not None:
        stmt = stmt.where(or_(Chunk.document_id.is_(None), Chunk.document_id != new_chunk.document_id))
    stmt = stmt.order_by("distance").limit(k)
    rows = (await db.execute(stmt)).all()
    return [(c, float(d)) for c, d in rows if d is not None and float(d) <= distance_threshold]


def _judge_sync(new_text: str, candidate_texts: List[str], model: str) -> tuple[List[ConflictFinding], int, int]:
    llm = ChatGoogleGenerativeAI(model=model, api_key=get_settings().gemini_api_key, temperature=0, timeout=20, max_retries=0).with_structured_output(ConflictJudgement, method="json_schema", include_raw=True)
    prompt = _build_conflict_prompt(new_text, candidate_texts)
    result = llm.invoke([SystemMessage(content=CONFLICT_SYSTEM_INSTRUCTION), HumanMessage(content=prompt)])
    if result["parsing_error"] is not None:
        raise ValueError(f"structured parse failed: {result['parsing_error']}")
    parsed: ConflictJudgement = result["parsed"]
    usage = getattr(result["raw"], "usage_metadata", None) or {}
    return parsed.findings, usage.get("input_tokens", 0) or 0, usage.get("output_tokens", 0) or 0


async def _judge_async(new_text: str, candidate_texts: List[str], model: str) -> tuple[List[ConflictFinding], int, int]:
    llm = ChatGoogleGenerativeAI(model=model, api_key=get_settings().gemini_api_key, temperature=0, timeout=20, max_retries=0).with_structured_output(ConflictJudgement, method="json_schema", include_raw=True)
    prompt = _build_conflict_prompt(new_text, candidate_texts)
    result = await llm.ainvoke([SystemMessage(content=CONFLICT_SYSTEM_INSTRUCTION), HumanMessage(content=prompt)])
    if result["parsing_error"] is not None:
        raise ValueError(f"structured parse failed: {result['parsing_error']}")
    parsed: ConflictJudgement = result["parsed"]
    usage = getattr(result["raw"], "usage_metadata", None) or {}
    return parsed.findings, usage.get("input_tokens", 0) or 0, usage.get("output_tokens", 0) or 0


def _findings_to_conflicts(findings: List[ConflictFinding], candidates: list[tuple[Chunk, float]]) -> list[tuple[Chunk, float, str]]:
    flagged = []
    for finding in findings:
        if not finding.conflicts:
            continue
        if finding.candidate_index < 0 or finding.candidate_index >= len(candidates):
            continue
        candidate, distance = candidates[finding.candidate_index]
        explanation = (finding.explanation or "").strip() or "The assistant judged these two entries to state conflicting facts."
        flagged.append((candidate, distance, explanation[:2000]))
    return flagged


def run_conflict_detection_sync(db: Session, college_id: int, new_chunk: Chunk, document_id: Optional[int] = None) -> int:
    """Sync entry point, for document ingestion (celery_tasks.py). Adds any
    new KnowledgeConflict rows to `db` but does NOT commit - the caller
    (which is looping over a document's chunks) commits once at the end.
    Returns how many conflicts were newly flagged for this chunk."""
    settings = get_settings()
    if not settings.conflict_detection_enabled:
        return 0
    try:
        candidates = _find_candidates_sync(db, college_id, new_chunk, k=settings.conflict_candidate_k, distance_threshold=settings.conflict_candidate_distance_threshold)
    except Exception:
        logger.warning("Conflict candidate search failed college_id=%s chunk_id=%s", college_id, new_chunk.chunk_id, exc_info=True)
        return 0
    if not candidates:
        return 0
    try:
        findings, input_tokens, output_tokens = _judge_sync(new_chunk.chunk_content, [c.chunk_content for c, _ in candidates], settings.conflict_detection_model)
        record_llm_cost_sync(db, college_id=college_id, document_id=document_id, stage=CONFLICT_DETECTION_STAGE, model=settings.conflict_detection_model, input_tokens=input_tokens, output_tokens=output_tokens)
    except Exception:
        logger.warning("Conflict judgement LLM call failed college_id=%s chunk_id=%s", college_id, new_chunk.chunk_id, exc_info=True)
        return 0

    created = 0
    for candidate, distance, explanation in _findings_to_conflicts(findings, candidates):
        exists = db.execute(
            select(KnowledgeConflict.conflict_id).where(
                KnowledgeConflict.college_id == college_id,
                KnowledgeConflict.new_chunk_id == new_chunk.chunk_id,
                KnowledgeConflict.existing_chunk_id == candidate.chunk_id,
            ).limit(1)
        ).scalars().first()
        if exists is not None:
            continue
        db.add(KnowledgeConflict(college_id=college_id, new_chunk_id=new_chunk.chunk_id, existing_chunk_id=candidate.chunk_id, similarity_distance=round(distance, 4), explanation=explanation, status="open"))
        created += 1
    if created:
        KNOWLEDGE_CONFLICTS_FLAGGED.labels(source_type=new_chunk.source_type).inc(created)
    return created


async def run_conflict_detection_async(db: AsyncSession, college_id: int, new_chunk: Chunk) -> int:
    """Async entry point, for the low-confidence reply and knowledge-base
    endpoints. `new_chunk` must already have a chunk_id (flush it first).
    Adds any new KnowledgeConflict rows to `db` but does NOT commit - the
    caller's own existing commit persists them alongside the write that
    triggered the check. Returns how many conflicts were newly flagged."""
    settings = get_settings()
    if not settings.conflict_detection_enabled or new_chunk.chunk_id is None:
        return 0
    try:
        candidates = await _find_candidates_async(db, college_id, new_chunk, k=settings.conflict_candidate_k, distance_threshold=settings.conflict_candidate_distance_threshold)
    except Exception:
        logger.warning("Conflict candidate search failed college_id=%s chunk_id=%s", college_id, new_chunk.chunk_id, exc_info=True)
        return 0
    if not candidates:
        return 0
    try:
        findings, input_tokens, output_tokens = await _judge_async(new_chunk.chunk_content, [c.chunk_content for c, _ in candidates], settings.conflict_detection_model)
        await record_llm_cost(db, college_id=college_id, student_id=None, session_id=None, stage=CONFLICT_DETECTION_STAGE, model=settings.conflict_detection_model, input_tokens=input_tokens, output_tokens=output_tokens)
    except Exception:
        logger.warning("Conflict judgement LLM call failed college_id=%s chunk_id=%s", college_id, new_chunk.chunk_id, exc_info=True)
        return 0

    created = 0
    for candidate, distance, explanation in _findings_to_conflicts(findings, candidates):
        exists = (
            await db.execute(
                select(KnowledgeConflict.conflict_id).where(
                    KnowledgeConflict.college_id == college_id,
                    KnowledgeConflict.new_chunk_id == new_chunk.chunk_id,
                    KnowledgeConflict.existing_chunk_id == candidate.chunk_id,
                ).limit(1)
            )
        ).scalars().first()
        if exists is not None:
            continue
        db.add(KnowledgeConflict(college_id=college_id, new_chunk_id=new_chunk.chunk_id, existing_chunk_id=candidate.chunk_id, similarity_distance=round(distance, 4), explanation=explanation, status="open"))
        created += 1
    if created:
        await db.flush()
        KNOWLEDGE_CONFLICTS_FLAGGED.labels(source_type=new_chunk.source_type).inc(created)
    return created
