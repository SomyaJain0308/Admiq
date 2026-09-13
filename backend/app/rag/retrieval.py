from backend.app.config import get_settings
from backend.app.models.Chunk import Chunk
from backend.app.models.College import College
from backend.app.models.Message import Message


from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langsmith import traceable

import logging
import time
from datetime import datetime, timezone


logger = logging.getLogger(__name__)



SYSTEM_PROMPT = """
You are Admiq, the WhatsApp pre-admission assistant for {college_name}. Help prospective students get accurate college-specific information and take the next useful admission step.

CONTEXT
Student profile: {student_summary}
Current session: {session_summary}
Previous assistant reply: {previous_assistant_message}
College strengths: {college_strengths}
Official college documents: {relevant_documents}
Student message: {query}

TRUTH
- Official college documents are the source of truth for college facts. Use college strengths only when relevant and consistent with them.
- Profile, summaries, and previous replies help resolve context but do not create new facts.
- Never guess or invent fees, eligibility, deadlines, placements, scholarships, rankings, approvals, seats, facilities, guarantees, or other college-specific facts.
- If the requested fact is not supported by the supplied context, say you do not have the exact official information and that the team will follow up. Set wants_human_handoff=true.
- If the student asks for a human, set wants_human_handoff=true.
- Never claim an outcome, response time, or action unless the context supports it.

ANSWERING
- Answer the direct question first.
- Resolve short follow-ups from conversation context, such as “and hostel?” or “how much is it?”. Preserve established topics and constraints.
- For multiple questions, answer each clearly. For comparisons, use only supported facts and do not invent a winner.
- Address concerns directly. Do not hide, deny, or manufacture negatives. If a concern is unsupported, say you cannot confirm it, then give relevant supported information if useful.
- Present genuine strengths confidently when relevant, but never use unsupported superlatives or marketing claims.

STYLE
- Natural WhatsApp admissions counsellor, not a brochure or FAQ bot.
- Concise: usually 1-4 short paragraphs or bullets.
- Match English, Hindi, or Hinglish naturally.
- Preserve supplied numbers, dates, names, and conditions exactly.
- No filler, corporate jargon, internal-system language, or source references.

FOLLOW-UP
Ask at most one question, and only when it helps the student's admission journey or resolves an important ambiguity. Do not force a question after greetings, thanks, acknowledgments, or a fully resolved request.

OUTPUT
Return the required fields:
- response: exact WhatsApp message for the student.
- updated_session_summary: concise internal summary of durable admissions context from this turn.
- sources: filenames/queries actually used; [] if no retrieval context was needed.
- wants_human_handoff: true only when exact information is unavailable and the response says the team will follow up, or when the student asks for a human. Otherwise false.

SESSION SUMMARY
Merge the previous session summary with this turn. Keep only useful admissions context: course interest, eligibility/scores, fees, scholarships, placement concerns, hostel, parent/guardian involvement, competing colleges, documents, deadlines, application stage, concerns, and next steps. Do not add unsupported facts, small talk, or information the student did not discuss.

The response field is the only field shown to the student.
"""




RESOLVE_QUERY_PROMPT = """
Route the student's latest WhatsApp message for college-document retrieval.

Previous assistant reply:
{previous_assistant_message}
Student message:
{query}

Return whether retrieval is needed and, if so, 1-4 focused English search queries.
- No retrieval for greetings, thanks, acknowledgments, or pure small talk.
- Retrieve for college-specific facts/actions: courses, fees, eligibility, scholarships, placements, hostel, facilities, documents, deadlines, application process, exams, approvals, seats, location, transport, or college-specific comparisons. When unsure, retrieve rather than risk a hallucination.
- Resolve pronouns and short follow-ups using the previous reply. Preserve established course, campus, gender/category, year, admission route, and other constraints.
- Use exactly 1 query for one topic. Use multiple only for genuinely distinct topics.
- Translate Hindi/Hinglish/other languages into clear English for retrieval.
- Queries must describe the information needed, not answer it.
"""




RE_QUERY_PROMPT = """
A college-document search returned poor matches. Rewrite each failed query so it is more likely to match official college wording while preserving the student's exact information need.

Student question:
{original_query}
Previous assistant reply:
{previous_assistant_message}
Failed queries:
{failed_queries}

Return exactly one rewritten English query per failed query, in the same order. Use useful synonyms, broader/narrower terms, or official terminology. Do not change the intended topic or add facts.
"""

settings = get_settings()



@traceable(name="embed_and_retrieve_chunks", run_type="retriever")
async def get_relevant_documents_scored(db, query: str, college_id: int, k: int) -> list[tuple[int, str, float]]:
    start = time.perf_counter()
    try:
        embedder = GoogleGenerativeAIEmbeddings(api_key=settings.gemini_api_key, model=settings.embedding_model, output_dimensionality=settings.vector_size)
        query_embedding = await embedder.aembed_query(query)
    except Exception as e:
        logger.error("Embedding call failed college_id=%s query=%r error=%s", college_id, query[:200], e, exc_info=True)
        raise # intentionally raised. Caller (agent.py's `retrieve()` node) catches this and falls back to a default SYSTEM_PROMPT so the conversation still continues. Do NOT call build_system_prompt() from anywhere that doesn't have an equivalent fallback in place this function is not safe to call bare.
    try:
        # Excludes staff-answer chunks whose expires_at has passed - without
        # this, the expiry staff pick when replying to a low-confidence
        # query (e.g. "scholarship deadline extended to Friday") was stored
        # but never enforced, so a stale time-boxed answer would keep being
        # retrieved and presented as current fact indefinitely. Document
        # chunks always have expires_at IS NULL (enforced by a DB check
        # constraint), so this never affects them.
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        results = await db.execute(
            select(Chunk, Chunk.embedding.cosine_distance(query_embedding).label("distance"))
            .where(Chunk.college_id == college_id, or_(Chunk.expires_at.is_(None), Chunk.expires_at > now))
            .options(selectinload(Chunk.document), selectinload(Chunk.source_query))
            .order_by("distance")
            .limit(k)
        )
        results = results.all()
    except Exception as e:
        logger.error("chunk retrieval query failed college_id=%s k=%s error=%s", college_id, k, e, exc_info=True)
        raise
    if not results:
        logger.info("No chunks found college_id=%s query=%r elapsed_ms=%.0f", college_id, query[:200], (time.perf_counter() - start) * 1000)
        return []
    scored= []
    for chunk, distance in results:
        try:
            if chunk.source_type == "document":
                source = chunk.document.file_name
            else:
                source = chunk.source_query.query_text if chunk.source_query else "Staff answer"
        except Exception as e:
            logger.warning("Skipping chunk with unresolved source college_id=%s chunk_id=%s error=%s", college_id, getattr(chunk, "chunk_id", "unknown"), e)
            continue
        block = f"Source: {source}\nContent: {chunk.chunk_content}"
        scored.append((chunk.chunk_id, block, distance))
    logger.info("Retrieved %d/%d chunks college_id=%s elapsed_ms=%.0f", len(scored), len(results), college_id, (time.perf_counter() - start) * 1000)
    return scored



async def get_previous_assistant_message(db, college_id: int, student_id: int) -> str:
    result = await db.execute(select(Message.content).where(Message.college_id == college_id, Message.student_id == student_id, Message.messager_role != 'student').order_by(Message.created_at.desc()).limit(1))
    message = result.scalars().first()
    return message or "This is the start of the conversation, no previous message yet."


@traceable(name="build_system_prompt")
async def build_system_prompt(db, query: str, college_id: int, student_id: int, session_id: int, relevant_documents: str, student_summary: str | None = None, session_summary: str | None = None) -> str:
    start = time.perf_counter()
    try:
        college_name_result = await db.execute(select(College.college_name).where(College.college_id == college_id).limit(1))
        college_name = college_name_result.scalars().first()
        college_strengths_result = await db.execute(select(College.college_strengths).where(College.college_id == college_id).limit(1))
        college_strengths = college_strengths_result.scalars().first()
        previous_assistant_message_result = await db.execute(select(Message.content).where(Message.college_id == college_id, Message.student_id == student_id, Message.messager_role != 'student').order_by(Message.created_at.desc()).limit(1))
        previous_assistant_message = previous_assistant_message_result.scalars().first()
    except Exception as e:
        logger.error("build_system_prompt failed college_id=%s student_id=%s session_id=%s error=%s", college_id, student_id, session_id, e, exc_info=True)
        raise  # intentionally raised — caller (agent.py's build_prompt node) must catch this and fall back to a default SYSTEM_PROMPT.
    prompt = SYSTEM_PROMPT.format(
        college_name=college_name,
        student_summary=student_summary or "No long-term student summary yet.",
        session_summary=session_summary or "No current session summary yet.",
        college_strengths=college_strengths or "No college-strengths was added by the college.",
        previous_assistant_message=previous_assistant_message or "This is the start of the conversation, no previous message yet.",
        query=query,
        relevant_documents=relevant_documents,
    )
    logger.debug("System prompt built college_id=%s student_id=%s session_id=%s elapsed_ms=%.0f", college_id, student_id, session_id, (time.perf_counter() - start) * 1000,)
    return prompt