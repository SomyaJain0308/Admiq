from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from datetime import datetime
from typing import List, Optional
import numpy as np


from backend.app.services.auth_services import verify_college_access
from backend.app.monitoring.logging_utils import get_logger
from backend.app.monitoring.low_confidence import LOW_CONFIDENCE_QUERIES_OPEN, LOW_CONFIDENCE_RESOLUTION_TIME_SECONDS, LOW_CONFIDENCE_QUERIES_RESOLVED
from backend.app.config import get_settings
from backend.app.services.whatsapp_service import send_staff_initiated_message
from backend.app.services.cost_service import record_whatsapp_cost, record_embedding_cost, estimate_tokens_from_text
from backend.app.database import get_db
from backend.app.models.LowConfidenceQuery import LowConfidenceQuery
from backend.app.models.Message import Message
from backend.app.models.Student import Student
from backend.app.models.StudentSession import StudentSession
from backend.app.models.WhatsappNumber import WhatsAppNumber
from backend.app.models.Chunk import Chunk
from backend.app.schemas.low_confidence import LowConfidenceResponse
from backend.app.models.CollegeStaff_StaffCollege import CollegeStaff
from backend.app.rag.staff_reply_context import reconstruct_staff_answer
from backend.app.rag.retrieval import get_relevant_documents_scored
from backend.app.rag.conflict_detection import run_conflict_detection_async
from backend.app.services.tenant_service import save_staff_message

logger = get_logger()

router = APIRouter(tags=["low_confidence"])

# How many existing chunks to surface for draft-assist / knowledge-base
# search. Suggestions run against the flagged question itself, so a tight
# k keeps the panel to genuinely close matches; search is staff-typed and
# more exploratory, so it gets a bit more room.
SUGGESTION_K = 5
KNOWLEDGE_SEARCH_K = 8

# Cap on how many open queries get pulled into one similarity-grouping pass.
# Queues this deep are rare, and if it happens, grouping just quietly stops
# covering the oldest overflow rather than embedding hundreds of questions
# on every poll.
SIMILAR_GROUP_MAX_QUERIES = 150
# Cosine similarity above which two flagged questions are treated as the
# "same question, different words" rather than merely related - high enough
# that unrelated questions sharing a topic (e.g. two different hostel
# questions) don't get bundled together and answered with the wrong reply.
SIMILAR_GROUP_COSINE_THRESHOLD = 0.86


def _parse_chunk_block(block: str) -> tuple[str, str]:
    """get_relevant_documents_scored returns each match pre-formatted as
    "Source: {source}\\nContent: {content}" for dropping straight into an LLM
    prompt. Staff-facing UI needs the two parts separately, so split back
    apart here instead of re-deriving the source label from the chunk (which
    would duplicate - and risk drifting from - the resolution logic already
    in retrieval.py).
    """
    source_label, _, content = block.partition("\nContent: ")
    return source_label.removeprefix("Source: "), content


def _extract_answer_text(content: str) -> str:
    """Staff-answer chunks are stored as "Question: ...\\nAnswer: ..." (see
    _resolve_single_query below). Pull just the answer portion so a "use
    this" click fills the reply box with something a student would actually
    receive, not the leading question line. Document chunks have no such
    marker and are returned as-is.
    """
    marker = "\nAnswer: "
    idx = content.find(marker)
    if idx == -1:
        return content
    return content[idx + len(marker):].strip()

@router.get("/router/low_confidence/{college_id}")
async def get_low_confidence_queries(
    college_id: int,
    resolved: bool = False,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    base_filter = (LowConfidenceQuery.college_id == college_id, LowConfidenceQuery.resolved == resolved)
    total = (await db.execute(select(func.count()).select_from(LowConfidenceQuery).where(*base_filter))).scalar_one()

    if not resolved:
        # Keep the live open-queue gauge reflecting the true total, not just
        # what's on the current page.
        LOW_CONFIDENCE_QUERIES_OPEN.set(total)

    # Oldest-flagged-first for the open queue - whoever's been waiting
    # longest should surface first, matching the "waiting time" column shown
    # on this page. For the resolved view, newest-resolved-first reads more
    # naturally as a recent-activity log instead.
    order_column = LowConfidenceQuery.resolved_at.desc() if resolved else LowConfidenceQuery.flagged_at.asc()
    low_confidence_result = await db.execute(
        select(LowConfidenceQuery).where(*base_filter).order_by(order_column).offset((page - 1) * page_size).limit(page_size)
    )
    low_confidence_queries = low_confidence_result.scalars().all()

    responses = []
    for query in low_confidence_queries:
        question_content_result = await db.execute(select(Message.content).where(Message.college_id == college_id, Message.message_id == query.question_message_id).limit(1))
        question_content = question_content_result.scalars().first()
        answer_content_result = await db.execute(select(Message.content).where(Message.college_id == college_id, Message.message_id == query.answer_message_id).limit(1))
        answer_content = answer_content_result.scalars().first()
        responses.append(LowConfidenceResponse(query_id=query.query_id, college_id=query.college_id, student_id=query.student_id, question_message_id=query.question_message_id, question_content=question_content, answer_message_id=query.answer_message_id, answer_content=answer_content, resolved=query.resolved, resolved_at=query.resolved_at if query.resolved_at else None, resolved_by=query.resolved_by if query.resolved_by else None, flagged_at=query.flagged_at))
    return {"items": responses, "total": total, "page": page, "page_size": page_size}



@router.get("/router/low_confidence/{college_id}/query/{query_id}", response_model=LowConfidenceResponse)
async def get_low_confidence_query(college_id: int, query_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    query_result = await db.execute(select(LowConfidenceQuery).where(LowConfidenceQuery.college_id == college_id, LowConfidenceQuery.query_id == query_id).limit(1))
    query = query_result.scalars().first()
    if not query:
        raise HTTPException(status_code=404, detail="Low confidence query not found")
    question_content_result = await db.execute(select(Message.content).where(Message.college_id == college_id, Message.message_id == query.question_message_id).limit(1))
    question_content = question_content_result.scalars().first()
    answer_content_result = await db.execute(select(Message.content).where(Message.college_id == college_id, Message.message_id == query.answer_message_id).limit(1))
    answer_content = answer_content_result.scalars().first()
    return LowConfidenceResponse(query_id=query.query_id, college_id=query.college_id, student_id=query.student_id, question_message_id=query.question_message_id, question_content=question_content, answer_message_id=query.answer_message_id, answer_content=answer_content, resolved=query.resolved, resolved_at=query.resolved_at if query.resolved_at else None, resolved_by=query.resolved_by if query.resolved_by else None, flagged_at=query.flagged_at)



async def _resolve_single_query(
    db: AsyncSession,
    college_id: int,
    query: LowConfidenceQuery,
    reply_message: str,
    expires_at: Optional[datetime],
    staff_id: int,
    settings,
    whatsapp_number: WhatsAppNumber,
) -> dict:
    """Sends reply_message to the student behind `query`, saves it as a real
    message, best-effort teaches it into the knowledge base, and marks the
    query resolved. Extracted so a bulk "same answer resolves N similar
    questions" reply (see additional_query_ids below) can run this once per
    student instead of duplicating the whole flow.
    """
    # Get last 4 message of the chat and get the question and answer from llm to store in db
    original_question_result = await db.execute(select(Message).where(Message.college_id == college_id, Message.message_id == query.question_message_id).limit(1))
    original_question = original_question_result.scalars().first()
    context_result = await db.execute(select(Message).where(Message.college_id == college_id, Message.student_id == query.student_id, Message.created_at <= original_question.created_at).order_by(Message.created_at.desc()).limit(4))
    recent_messages = list(reversed(context_result.scalars().all())) # If you sorted ASC and took LIMIT 4 instead, you'd get the 4 oldest messages in that student's entire history, not the 4 closest to this question — wrong messages entirely. So DESC is required for correctness of which rows come back. But DESC also means the rows arrive in the wrong order for feeding to an LLM as a conversation — you'd get [newest, ..., oldest]
    recent_conversation = "\n".join(f"{m.messager_role}: {m.content}" for m in recent_messages)
    # save + send the staff reply as a real message
    # NOTE: reconstruction (the LLM call that turns this into a reusable
    # Q&A pair) used to happen here, before the reply was even sent. That
    # meant a flaky/timed-out LLM call (max_retries=0, 15s timeout) killed
    # the whole request with an unhandled exception - the student never
    # got the reply, nothing was saved, and the query stayed stuck open.
    # The reply itself must never depend on the "teach the database" step
    # succeeding, so sending/saving happens first unconditionally, and
    # reconstruction+embedding is attempted afterwards as a best-effort
    # step (see below) that can fail without losing the reply.
    student_result = await db.execute(select(Student).where(Student.college_id == college_id, Student.student_id == query.student_id).limit(1))
    student = student_result.scalars().first()
    await save_staff_message(db, college_id=college_id, student_id=query.student_id, staff_id=staff_id, content=reply_message, session_id=original_question.session_id)

    # Same 24h customer-service-window concern as the direct-message
    # endpoint applies here if anything more so - a low-confidence query can
    # sit unanswered for a while before staff get to it, so by the time a
    # reply goes out the window has very plausibly already closed.
    last_session_result = await db.execute(
        select(StudentSession.last_message_at)
        .where(StudentSession.college_id == college_id, StudentSession.student_id == query.student_id)
        .order_by(StudentSession.last_message_at.desc())
        .limit(1)
    )
    last_inbound_message_at = last_session_result.scalars().first()
    send_result = await send_staff_initiated_message(
        phone_number_id=whatsapp_number.phone_number_id,
        to=student.whatsapp_user_id,
        message=reply_message,
        access_token=settings.whatsapp_access_token,
        last_inbound_message_at=last_inbound_message_at,
        template_name=settings.whatsapp_staff_template_name,
        template_language_code=settings.whatsapp_staff_template_language_code,
    )
    if not send_result["ok"]:
        logger.error(f"Failed to deliver staff reply to student_id={query.student_id} (channel={send_result.get('channel')})")
    # channel="text" means it went out as a free-form reply inside the 24h window ("session" cost);
    # channel="template" means the window was closed and it fell back to the approved template ("utility" cost).
    await record_whatsapp_cost(db, college_id=college_id, student_id=query.student_id, session_id=original_question.session_id, category="utility" if send_result.get("channel") == "template" else "session", success=send_result["ok"])

    # Teach the database: reconstruct a self-contained Q&A pair and embed
    # it as a retrievable chunk. Best-effort - if the LLM call or embedding
    # call fails (timeout, rate limit, parse error), the reply has ALREADY
    # been sent and saved above, so we log it, surface it in the response,
    # and still resolve the queue item rather than leaving it stuck open
    # and stuck un-teachable forever.
    saved_as_answer = False
    reconstructed_question = None
    save_error = None
    conflicts_flagged = 0
    try:
        reconstructed = reconstruct_staff_answer(recent_conversation, reply_message)
        embedder = GoogleGenerativeAIEmbeddings(model=settings.embedding_model, api_key=settings.gemini_api_key, output_dimensionality=settings.vector_size)
        chunk_text = f"Question: {reconstructed.question}\nAnswer: {reconstructed.answer}"
        vector = await embedder.aembed_query(chunk_text)
        await record_embedding_cost(db, college_id=college_id, student_id=query.student_id, session_id=original_question.session_id, stage="staff_answer_embedding", model=settings.embedding_model, input_tokens=estimate_tokens_from_text(chunk_text))
        new_chunk = Chunk(college_id=college_id, chunk_content=chunk_text, embedding=vector, chunk_index=0, source_type="staff_answer", source_query_id=query.query_id, expires_at=expires_at, created_by=staff_id)
        db.add(new_chunk)
        saved_as_answer = True
        reconstructed_question = reconstructed.question
        # Best-effort: flush to get new_chunk.chunk_id (needed to exclude it
        # from its own candidate search and to reference it on any
        # conflict row), then check it against the rest of the knowledge
        # base. Never raised past this point - a failure here should never
        # turn an otherwise-successful reply into a "save failed" one.
        try:
            await db.flush()
            conflicts_flagged = await run_conflict_detection_async(db, college_id=college_id, new_chunk=new_chunk)
        except Exception:
            logger.warning(f"Conflict detection failed for query_id={query.query_id}, college_id={college_id}", exc_info=True)
    except Exception:
        logger.error(f"Failed to save staff reply as a reusable answer for query_id={query.query_id}, college_id={college_id}", exc_info=True)
        save_error = "Reply was sent, but saving it for future students failed. You can re-save it from the student's conversation."

    query.resolved = True
    query.resolved_by = staff_id
    query.resolved_at = datetime.utcnow()
    LOW_CONFIDENCE_QUERIES_RESOLVED.inc()
    LOW_CONFIDENCE_RESOLUTION_TIME_SECONDS.observe((query.resolved_at - query.flagged_at).total_seconds())

    return {
        "query_id": query.query_id,
        "reconstructed_question": reconstructed_question,
        "channel": send_result.get("channel", "text"),
        "saved_as_answer": saved_as_answer,
        "save_error": save_error,
        "conflicts_flagged": conflicts_flagged,
    }


@router.post("/router/low_confidence/{college_id}/query/{query_id}/reply")
async def reply_to_low_confidence_query(
    college_id: int,
    query_id: int,
    reply_message: str,
    expires_at: Optional[datetime] = None,
    additional_query_ids: Optional[List[int]] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    staff_id = membership.staff_id
    settings = get_settings()
    query_result = await db.execute(select(LowConfidenceQuery).where(LowConfidenceQuery.college_id == college_id, LowConfidenceQuery.query_id == query_id, LowConfidenceQuery.resolved == False).limit(1))
    query = query_result.scalars().first()
    if query is None:
        raise HTTPException(status_code=404, detail="Low Confidence Query not found")

    whatsapp_number_result = await db.execute(select(WhatsAppNumber).where(WhatsAppNumber.college_id == college_id).limit(1))
    whatsapp_number = whatsapp_number_result.scalars().first()

    primary_result = await _resolve_single_query(db, college_id, query, reply_message, expires_at, staff_id, settings, whatsapp_number)

    # additional_query_ids lets one reply resolve a whole cluster of
    # duplicate-looking open questions at once (see the similar-groups
    # endpoint below) instead of staff retyping the same answer for each
    # student individually. Anything already resolved, or not actually an
    # open query in this college, is silently skipped rather than failing
    # the whole request over a stale id - the queue can move between when
    # the group was fetched and when staff hits send.
    resolved_additional = []
    if additional_query_ids:
        additional_ids = [qid for qid in dict.fromkeys(additional_query_ids) if qid != query_id]
        if additional_ids:
            additional_result = await db.execute(
                select(LowConfidenceQuery).where(
                    LowConfidenceQuery.college_id == college_id,
                    LowConfidenceQuery.query_id.in_(additional_ids),
                    LowConfidenceQuery.resolved == False,
                )
            )
            for additional_query in additional_result.scalars().all():
                resolved_additional.append(
                    await _resolve_single_query(db, college_id, additional_query, reply_message, expires_at, staff_id, settings, whatsapp_number)
                )

    await db.commit()

    return {
        "status": "resolved",
        "reconstructed_question": primary_result["reconstructed_question"],
        "expires_at": expires_at,
        "channel": primary_result["channel"],
        "saved_as_answer": primary_result["saved_as_answer"],
        "save_error": primary_result["save_error"],
        "conflicts_flagged": primary_result["conflicts_flagged"],
        "resolved_additional": resolved_additional,
    }


@router.get("/router/low_confidence/{college_id}/query/{query_id}/suggestions")
async def get_reply_suggestions(college_id: int, query_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    """Draft-assist: retrieval already ran once for this question (that's
    why it ended up in the queue) - re-run it against the flagged question
    itself so staff see the closest things already in the knowledge base
    before typing a reply from scratch, and can 1-click "use this" or edit
    instead.
    """
    query_result = await db.execute(select(LowConfidenceQuery).where(LowConfidenceQuery.college_id == college_id, LowConfidenceQuery.query_id == query_id).limit(1))
    query = query_result.scalars().first()
    if query is None:
        raise HTTPException(status_code=404, detail="Low Confidence Query not found")
    question_content_result = await db.execute(select(Message.content).where(Message.college_id == college_id, Message.message_id == query.question_message_id).limit(1))
    question_content = question_content_result.scalars().first()
    if not question_content:
        return {"suggestions": []}
    try:
        scored = await get_relevant_documents_scored(db, query=question_content, college_id=college_id, k=SUGGESTION_K)
    except Exception:
        logger.error("Failed to fetch reply suggestions query_id=%s college_id=%s", query_id, college_id, exc_info=True)
        return {"suggestions": []}
    suggestions = []
    for chunk_id, block, distance in scored:
        source_label, content = _parse_chunk_block(block)
        suggestions.append({
            "chunk_id": chunk_id,
            "source_label": source_label,
            "content": content,
            "answer_text": _extract_answer_text(content),
            "distance": round(float(distance), 4),
        })
    return {"suggestions": suggestions}


@router.get("/router/low_confidence/{college_id}/knowledge-search")
async def search_knowledge_base(college_id: int, q: str, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    """Lets staff search everything already in the knowledge base (documents
    and past staff answers alike) while composing a reply, so they don't end
    up accidentally contradicting something already answered.
    """
    q = q.strip()
    if not q:
        return {"results": []}
    try:
        scored = await get_relevant_documents_scored(db, query=q, college_id=college_id, k=KNOWLEDGE_SEARCH_K)
    except Exception:
        logger.error("Knowledge base search failed college_id=%s q=%r", college_id, q[:200], exc_info=True)
        raise HTTPException(status_code=502, detail="Search failed. Please try again.")
    results = []
    for chunk_id, block, distance in scored:
        source_label, content = _parse_chunk_block(block)
        results.append({
            "chunk_id": chunk_id,
            "source_label": source_label,
            "content": content,
            "answer_text": _extract_answer_text(content),
            "distance": round(float(distance), 4),
        })
    return {"results": results}


@router.get("/router/low_confidence/{college_id}/similar-groups")
async def get_similar_open_query_groups(college_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    """Groups currently-open queries whose flagged questions look like the
    same underlying question in different words, so staff can spot "five
    students asked this" and resolve the whole cluster with one reply
    (see additional_query_ids on the reply endpoint) instead of answering
    the same thing five separate times.
    """
    settings = get_settings()
    open_result = await db.execute(
        select(LowConfidenceQuery)
        .where(LowConfidenceQuery.college_id == college_id, LowConfidenceQuery.resolved == False)
        .order_by(LowConfidenceQuery.flagged_at.asc())
        .limit(SIMILAR_GROUP_MAX_QUERIES)
    )
    open_queries = open_result.scalars().all()
    if len(open_queries) < 2:
        return {"groups": []}

    # Pull every flagged question's text in one round trip rather than one
    # per query.
    question_ids = [q.question_message_id for q in open_queries]
    content_result = await db.execute(select(Message.message_id, Message.content).where(Message.college_id == college_id, Message.message_id.in_(question_ids)))
    content_by_message_id = dict(content_result.all())

    items = [(q, content_by_message_id.get(q.question_message_id)) for q in open_queries]
    items = [(q, c) for q, c in items if c]
    if len(items) < 2:
        return {"groups": []}

    try:
        embedder = GoogleGenerativeAIEmbeddings(model=settings.embedding_model, api_key=settings.gemini_api_key, output_dimensionality=settings.vector_size)
        vectors = await embedder.aembed_documents([c for _, c in items])
    except Exception:
        logger.error("Failed to embed open queries for similarity grouping college_id=%s", college_id, exc_info=True)
        return {"groups": []}

    matrix = np.array(vectors)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1  # guards against a degenerate all-zero embedding rather than dividing by it
    normalized = matrix / norms
    similarity = normalized @ normalized.T

    # Union-find over the "similar enough" pairs so a chain of near-duplicate
    # phrasings (A~B, B~C, ...) all land in one group instead of just the
    # single closest pair.
    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            if similarity[i, j] >= SIMILAR_GROUP_COSINE_THRESHOLD:
                union(i, j)

    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)

    groups = []
    for indices in clusters.values():
        if len(indices) < 2:
            continue
        members = []
        for i in indices:
            q, content = items[i]
            members.append({
                "query_id": q.query_id,
                "student_id": q.student_id,
                "question_message_id": q.question_message_id,
                "question_content": content,
                "flagged_at": q.flagged_at,
            })
        members.sort(key=lambda m: m["flagged_at"])
        groups.append({"query_ids": [m["query_id"] for m in members], "members": members})

    groups.sort(key=lambda g: len(g["members"]), reverse=True)
    return {"groups": groups}
