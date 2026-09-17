from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models.Chunk import Chunk
from backend.app.models.Document import Document
from backend.app.models.KnowledgeConflict import KnowledgeConflict
from backend.app.models.CollegeStaff_StaffCollege import CollegeStaff
from backend.app.services.auth_services import verify_college_access
from backend.app.schemas.knowledge_conflicts import ConflictChunkInfo, KnowledgeConflictResponse
from backend.app.api.v1.routers.knowledge_base import parse_qa_chunk
from backend.app.monitoring.knowledge_conflicts import KNOWLEDGE_CONFLICTS_OPEN, KNOWLEDGE_CONFLICTS_REVIEWED
from backend.app.monitoring.logging_utils import get_logger

logger = get_logger()

router = APIRouter(tags=["knowledge_conflicts"])


def _chunk_info(chunk: Chunk, now: datetime, file_name_by_document_id: dict[int, str]) -> ConflictChunkInfo:
    if chunk.source_type == "document":
        label = file_name_by_document_id.get(chunk.document_id, "Deleted document")
    else:
        question, _ = parse_qa_chunk(chunk.chunk_content)
        label = f"Staff answer: {question}" if question else "Knowledge base entry"
    return ConflictChunkInfo(
        chunk_id=chunk.chunk_id,
        content=chunk.chunk_content,
        source_type=chunk.source_type,
        source_label=label,
        document_id=chunk.document_id,
        is_expired=chunk.expires_at is not None and chunk.expires_at <= now,
    )


async def _serialize_conflicts(db: AsyncSession, college_id: int, conflicts: list[KnowledgeConflict]) -> list[KnowledgeConflictResponse]:
    if not conflicts:
        return []
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    chunk_ids = {c.new_chunk_id for c in conflicts} | {c.existing_chunk_id for c in conflicts}
    chunks_result = await db.execute(select(Chunk).where(Chunk.college_id == college_id, Chunk.chunk_id.in_(chunk_ids)))
    chunk_by_id = {c.chunk_id: c for c in chunks_result.scalars().all()}

    document_ids = {c.document_id for c in chunk_by_id.values() if c.document_id is not None}
    file_name_by_document_id: dict[int, str] = {}
    if document_ids:
        docs_result = await db.execute(select(Document.document_id, Document.file_name).where(Document.college_id == college_id, Document.document_id.in_(document_ids)))
        file_name_by_document_id = dict(docs_result.all())

    resolver_ids = {c.resolved_by for c in conflicts if c.resolved_by is not None}
    staff_name_by_id: dict[int, str] = {}
    if resolver_ids:
        staff_result = await db.execute(select(CollegeStaff.staff_id, CollegeStaff.staff_name).where(CollegeStaff.staff_id.in_(resolver_ids)))
        staff_name_by_id = dict(staff_result.all())

    items = []
    for c in conflicts:
        new_chunk = chunk_by_id.get(c.new_chunk_id)
        existing_chunk = chunk_by_id.get(c.existing_chunk_id)
        if new_chunk is None or existing_chunk is None:
            # One side was deleted after the conflict was flagged but before
            # the cascading FK cleanup caught up (or this row is stale from
            # before that cascade existed) - skip rather than 500.
            continue
        items.append(
            KnowledgeConflictResponse(
                conflict_id=c.conflict_id,
                college_id=c.college_id,
                status=c.status,
                explanation=c.explanation,
                similarity_distance=float(c.similarity_distance) if c.similarity_distance is not None else None,
                new_chunk=_chunk_info(new_chunk, now, file_name_by_document_id),
                existing_chunk=_chunk_info(existing_chunk, now, file_name_by_document_id),
                created_at=c.created_at,
                resolved_by=c.resolved_by,
                resolved_by_name=staff_name_by_id.get(c.resolved_by) if c.resolved_by else None,
                resolved_at=c.resolved_at,
            )
        )
    return items


@router.get("/router/colleges/{college_id}/knowledge-conflicts")
async def list_knowledge_conflicts(
    college_id: int,
    status: str = "open",
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    if status not in ("open", "resolved", "dismissed", "all"):
        raise HTTPException(status_code=400, detail="status must be one of: open, resolved, dismissed, all")
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    filters = [KnowledgeConflict.college_id == college_id]
    if status != "all":
        filters.append(KnowledgeConflict.status == status)

    total = (await db.execute(select(func.count()).select_from(KnowledgeConflict).where(*filters))).scalar_one()

    if status == "open":
        # Keep the live open-conflicts gauge reflecting the true total, not
        # just what's on the current page - same pattern as the
        # low-confidence queue's open-queue gauge.
        KNOWLEDGE_CONFLICTS_OPEN.set(total)

    # Oldest-flagged-first for open conflicts (whoever's been sitting longest
    # surfaces first); newest-first for a reviewed history, which reads more
    # naturally as a recent-activity log.
    order_column = KnowledgeConflict.created_at.asc() if status == "open" else KnowledgeConflict.created_at.desc()
    result = await db.execute(select(KnowledgeConflict).where(*filters).order_by(order_column).offset((page - 1) * page_size).limit(page_size))
    conflicts = result.scalars().all()
    items = await _serialize_conflicts(db, college_id, conflicts)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/router/colleges/{college_id}/knowledge-conflicts/{conflict_id}", response_model=KnowledgeConflictResponse)
async def get_knowledge_conflict(college_id: int, conflict_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    result = await db.execute(select(KnowledgeConflict).where(KnowledgeConflict.college_id == college_id, KnowledgeConflict.conflict_id == conflict_id).limit(1))
    conflict = result.scalars().first()
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found.")
    items = await _serialize_conflicts(db, college_id, [conflict])
    if not items:
        raise HTTPException(status_code=404, detail="Conflict not found.")
    return items[0]


async def _review_conflict(college_id: int, conflict_id: int, new_status: str, db: AsyncSession, membership: CollegeStaff) -> KnowledgeConflictResponse:
    result = await db.execute(select(KnowledgeConflict).where(KnowledgeConflict.college_id == college_id, KnowledgeConflict.conflict_id == conflict_id, KnowledgeConflict.status == "open").limit(1))
    conflict = result.scalars().first()
    if conflict is None:
        raise HTTPException(status_code=404, detail="Open conflict not found.")
    conflict.status = new_status
    conflict.resolved_by = membership.staff_id
    conflict.resolved_at = datetime.utcnow()
    KNOWLEDGE_CONFLICTS_REVIEWED.labels(outcome=new_status).inc()
    await db.commit()
    await db.refresh(conflict)
    items = await _serialize_conflicts(db, college_id, [conflict])
    return items[0]


@router.post("/router/colleges/{college_id}/knowledge-conflicts/{conflict_id}/resolve", response_model=KnowledgeConflictResponse)
async def resolve_knowledge_conflict(college_id: int, conflict_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    """Staff has fixed the underlying content (edited the knowledge-base
    entry, replaced/deleted the document, etc.) and is marking this pair as
    dealt with. Doesn't touch either chunk itself - purely a review-status
    change on the flag."""
    return await _review_conflict(college_id, conflict_id, "resolved", db, membership)


@router.post("/router/colleges/{college_id}/knowledge-conflicts/{conflict_id}/dismiss", response_model=KnowledgeConflictResponse)
async def dismiss_knowledge_conflict(college_id: int, conflict_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    """Staff looked at the pair and decided it isn't actually a conflict
    (e.g. two genuinely different courses/categories that just read as
    similar to the model)."""
    return await _review_conflict(college_id, conflict_id, "dismissed", db, membership)
