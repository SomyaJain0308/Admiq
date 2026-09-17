from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from backend.app.database import get_db
from backend.app.config import get_settings
from backend.app.models.Chunk import Chunk
from backend.app.models.CollegeStaff_StaffCollege import CollegeStaff
from backend.app.models.LowConfidenceQuery import LowConfidenceQuery
from backend.app.models.Message import Message
from backend.app.services.auth_services import verify_college_access
from backend.app.services.cost_service import record_embedding_cost, estimate_tokens_from_text
from backend.app.schemas.knowledge_base import KnowledgeBaseEntry, CreateKnowledgeBaseEntry, UpdateKnowledgeBaseEntry
from backend.app.rag.conflict_detection import run_conflict_detection_async
from backend.app.monitoring.logging_utils import get_logger

logger = get_logger()

router = APIRouter(tags=["knowledge_base"])

# Days out a staff answer's expiry has to be before it shows up in the
# "expiring soon" filter - long enough that staff notice it before it
# actually lapses and starts getting silently excluded from retrieval
# (see rag/retrieval.py), short enough that it isn't just "everything with
# any expiry at all".
EXPIRING_SOON_DAYS = 14

# Below this many retrievals since creation, an entry counts as "rarely
# used" for the utilization filter - deliberately generous (this isn't
# "never used", just "not obviously earning its keep") since a brand-new
# entry hasn't had time to be retrieved yet either.
LOW_USAGE_THRESHOLD = 2


def format_qa_chunk(question: str, answer: str) -> str:
    """Matches the "Question: ...\\nAnswer: ..." shape staff_reply_context.py
    already writes for reactively-resolved answers, so proactively-added
    entries are embedded/retrieved identically - retrieval.py and
    low_confidence.py's suggestion/search endpoints don't need to know which
    path a given chunk came from.
    """
    return f"Question: {question.strip()}\nAnswer: {answer.strip()}"


def parse_qa_chunk(chunk_content: str) -> tuple[str, str]:
    """Inverse of format_qa_chunk - best-effort, since a chunk could in
    principle be hand-edited into something that no longer matches the
    shape exactly. Falls back to treating the whole thing as the answer
    with an empty question rather than raising.
    """
    marker = "\nAnswer:"
    if chunk_content.startswith("Question:") and marker in chunk_content:
        q_part, _, a_part = chunk_content.partition(marker)
        return q_part[len("Question:"):].strip(), a_part.strip()
    return "", chunk_content.strip()


async def _embed_qa(question: str, answer: str) -> tuple[str, list[float], int]:
    settings = get_settings()
    chunk_text = format_qa_chunk(question, answer)
    embedder = GoogleGenerativeAIEmbeddings(model=settings.embedding_model, api_key=settings.gemini_api_key, output_dimensionality=settings.vector_size)
    try:
        vector = await embedder.aembed_query(chunk_text)
    except Exception as e:
        logger.error("Failed to embed knowledge-base entry error=%s", e, exc_info=True)
        raise HTTPException(status_code=502, detail="Failed to save - the embedding service is unavailable right now. Please try again.")
    return chunk_text, vector, estimate_tokens_from_text(chunk_text)


async def _serialize_entries(db: AsyncSession, college_id: int, chunks: list[Chunk], conflicts_flagged_by_chunk_id: dict[int, int] | None = None) -> list[KnowledgeBaseEntry]:
    if not chunks:
        return []
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    source_query_ids = [c.source_query_id for c in chunks if c.source_query_id is not None]
    original_question_by_query_id: dict[int, str] = {}
    if source_query_ids:
        rows = await db.execute(
            select(LowConfidenceQuery.query_id, Message.content)
            .join(Message, (Message.college_id == LowConfidenceQuery.college_id) & (Message.message_id == LowConfidenceQuery.question_message_id))
            .where(LowConfidenceQuery.college_id == college_id, LowConfidenceQuery.query_id.in_(source_query_ids))
        )
        original_question_by_query_id = dict(rows.all())

    created_by_ids = {c.created_by for c in chunks if c.created_by is not None}
    staff_name_by_id: dict[int, str] = {}
    if created_by_ids:
        rows = await db.execute(select(CollegeStaff.staff_id, CollegeStaff.staff_name).where(CollegeStaff.staff_id.in_(created_by_ids)))
        staff_name_by_id = dict(rows.all())

    conflicts_flagged_by_chunk_id = conflicts_flagged_by_chunk_id or {}
    entries = []
    for c in chunks:
        question, answer = parse_qa_chunk(c.chunk_content)
        entries.append(
            KnowledgeBaseEntry(
                chunk_id=c.chunk_id,
                question=question,
                answer=answer,
                origin="reactive" if c.source_query_id is not None else "proactive",
                source_query_id=c.source_query_id,
                original_question=original_question_by_query_id.get(c.source_query_id) if c.source_query_id else None,
                expires_at=c.expires_at,
                is_expired=c.expires_at is not None and c.expires_at <= now,
                retrieval_count=c.retrieval_count,
                last_retrieved_at=c.last_retrieved_at,
                created_at=c.created_at,
                created_by=c.created_by,
                created_by_name=staff_name_by_id.get(c.created_by) if c.created_by else None,
                conflicts_flagged=conflicts_flagged_by_chunk_id.get(c.chunk_id, 0),
            )
        )
    return entries


@router.get("/router/colleges/{college_id}/knowledge-base")
async def list_knowledge_base(
    college_id: int,
    search: str | None = None,
    expiring_soon: bool = False,
    unused: bool = False,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    filters = [Chunk.college_id == college_id, Chunk.source_type == "staff_answer"]
    search = (search or "").strip()
    if search:
        filters.append(Chunk.chunk_content.ilike(f"%{search}%"))
    if expiring_soon:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        filters.append(Chunk.expires_at.is_not(None))
        filters.append(Chunk.expires_at <= now + timedelta(days=EXPIRING_SOON_DAYS))
    if unused:
        filters.append(Chunk.retrieval_count < LOW_USAGE_THRESHOLD)

    total = (await db.execute(select(func.count()).select_from(Chunk).where(*filters))).scalar_one()

    result = await db.execute(
        select(Chunk).where(*filters).order_by(Chunk.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    chunks = result.scalars().all()
    items = await _serialize_entries(db, college_id, chunks)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/router/colleges/{college_id}/knowledge-base", response_model=KnowledgeBaseEntry)
async def create_knowledge_base_entry(
    college_id: int,
    payload: CreateKnowledgeBaseEntry,
    db: AsyncSession = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    """Lets staff teach the assistant something proactively - e.g. ahead of
    an admissions deadline they already know students will ask about -
    instead of only ever reacting to a flagged student question. Same
    "Question: ...\\nAnswer: ..." embedding shape as a reactively-resolved
    answer (see format_qa_chunk), so it's retrieved identically; the only
    difference is source_query_id stays NULL, since there's no flagged
    query behind it.
    """
    chunk_text, vector, input_tokens = await _embed_qa(payload.question, payload.answer)
    chunk = Chunk(
        college_id=college_id,
        chunk_content=chunk_text,
        embedding=vector,
        chunk_index=0,
        source_type="staff_answer",
        source_query_id=None,
        expires_at=payload.expires_at,
        created_by=membership.staff_id,
    )
    db.add(chunk)
    await record_embedding_cost(db, college_id=college_id, student_id=None, session_id=None, stage="knowledge_base_manual_entry", model=get_settings().embedding_model, input_tokens=input_tokens)
    # Flush (not commit) to get chunk.chunk_id, so the proactive entry can be
    # checked against the rest of the knowledge base and, if it conflicts
    # with something, have that flag reference it. Best-effort - never lets
    # a flaky conflict-check call turn an otherwise-successful save into a
    # failed one.
    await db.flush()
    conflicts_flagged = 0
    try:
        conflicts_flagged = await run_conflict_detection_async(db, college_id=college_id, new_chunk=chunk)
    except Exception:
        logger.warning("Conflict detection failed for new knowledge-base entry college_id=%s", college_id, exc_info=True)
    await db.commit()
    await db.refresh(chunk)
    entries = await _serialize_entries(db, college_id, [chunk], {chunk.chunk_id: conflicts_flagged})
    return entries[0]


@router.patch("/router/colleges/{college_id}/knowledge-base/{chunk_id}", response_model=KnowledgeBaseEntry)
async def update_knowledge_base_entry(
    college_id: int,
    chunk_id: int,
    payload: UpdateKnowledgeBaseEntry,
    db: AsyncSession = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    result = await db.execute(select(Chunk).where(Chunk.college_id == college_id, Chunk.chunk_id == chunk_id, Chunk.source_type == "staff_answer"))
    chunk = result.scalars().first()
    if chunk is None:
        raise HTTPException(status_code=404, detail="Knowledge base entry not found.")

    content_changed = payload.question is not None or payload.answer is not None
    if content_changed:
        # Content changed - re-embed. Re-parsing the existing content for
        # whichever half wasn't sent keeps a partial edit (e.g. just fixing
        # the answer) from silently dropping the other half.
        current_question, current_answer = parse_qa_chunk(chunk.chunk_content)
        new_question = payload.question if payload.question is not None else current_question
        new_answer = payload.answer if payload.answer is not None else current_answer
        chunk_text, vector, input_tokens = await _embed_qa(new_question, new_answer)
        chunk.chunk_content = chunk_text
        chunk.embedding = vector
        await record_embedding_cost(db, college_id=college_id, student_id=None, session_id=None, stage="knowledge_base_edit", model=get_settings().embedding_model, input_tokens=input_tokens)

    if payload.clear_expiry:
        chunk.expires_at = None
    elif payload.expires_at is not None:
        chunk.expires_at = payload.expires_at

    conflicts_flagged = 0
    if content_changed:
        # Only worth re-checking when the actual wording changed - editing
        # just the expiry date doesn't change what fact this entry states.
        # Best-effort, same reasoning as the create path above.
        try:
            await db.flush()
            conflicts_flagged = await run_conflict_detection_async(db, college_id=college_id, new_chunk=chunk)
        except Exception:
            logger.warning("Conflict detection failed for edited knowledge-base entry chunk_id=%s college_id=%s", chunk_id, college_id, exc_info=True)

    await db.commit()
    await db.refresh(chunk)
    entries = await _serialize_entries(db, college_id, [chunk], {chunk.chunk_id: conflicts_flagged})
    return entries[0]


@router.delete("/router/colleges/{college_id}/knowledge-base/{chunk_id}", status_code=204)
async def delete_knowledge_base_entry(
    college_id: int,
    chunk_id: int,
    db: AsyncSession = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    result = await db.execute(select(Chunk).where(Chunk.college_id == college_id, Chunk.chunk_id == chunk_id, Chunk.source_type == "staff_answer"))
    chunk = result.scalars().first()
    if chunk is None:
        raise HTTPException(status_code=404, detail="Knowledge base entry not found.")
    await db.delete(chunk)
    await db.commit()
