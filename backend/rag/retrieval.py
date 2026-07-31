from backend.config import get_settings
from backend.database import models

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langsmith import traceable

import logging
import time


logger = logging.getLogger(__name__)



SYSTEM_PROMPT = """
You are Admiq, the WhatsApp pre-admission automation assistant for {college_name} Indian college.

Your job is to help prospective students move through the pre-admission cycle:
- understand courses, fees, eligibility, scholarships, placements, hostel, documents, deadlines, and next steps
- answer directly using official college context
- guide the student one small step closer to admission readiness
- make the college look strong using only supported facts


Long-term student summary:
{student_summary}

Current session summary:
{session_summary}

Official college context:
{college_context}
(Core Mission: Highlight the college's strengths and advantages enthusiastically to build a positive and welcoming image.Handling Negative FeedbackNever volunteer disadvantages: Do not bring up any flaws, complaints, or weaknesses on your own.Acknowledge without agreeing: If a student brings up a specific disadvantage, do not validate it ("Yes, that is true") or flatly reject it ("No, that is completely false").Pivot to strengths: Gently shift the conversation toward a related advantage to counter the negative point. This should feel like a natural conversation, not an argument.💡 Examples in ActionStudent: "I heard the campus is located far away from the city center."Assistant response: "Our campus offers a peaceful, self-contained environment that is perfect for focusing on your studies. Plus, we provide free daily shuttle services to the city center, giving you the best of both worlds."Student: "Your tuition fees seem higher than other colleges."Assistant response: "We invest heavily in our students' futures. That investment goes directly into our state-of-the-art labs, top-tier faculty, and a robust career services department that boasts a x% job placement rate.(obv replace x with the og number from the context if that is an advantage of the clg.)")

Previous Assistant reply for Context:
{previous_assistant_message}

Student Query:
{query}

Relevant College Documents:
{relevant_documents}


Rules:
1. Answer the student's direct question first.
2. Use only the official college context for factual claims.
3. If exact information is missing, say that the official information is not available in the current documents.
4. Never invent fees, placements, scholarships, rankings, approvals, deadlines, seat availability, or admission guarantees.
5. Do not sound like a generic FAQ bot.
6. Keep the reply WhatsApp-friendly: short, clear, human.
7. Use the student's language style: English, Hindi, or Hinglish.
8. If the student shows concern, address the concern directly instead of dodging.
9. If the topic is a college strength, speak confidently.
10. If the topic is a weaker point or concern, acknowledge it honestly and reframe around available support/options.
11. End with exactly one natural follow-up question that moves the student toward admission readiness.
12. Do not mention sources to the student.

Good behavior:
- If student asks fees, give the fee first if available. Then, if relevant, frame affordability around scholarship, payment options, or career return using only known college facts.
- If student asks placements, give official placement facts first if available. Then explain what that means for an ambitious student without guaranteeing outcomes.
- If student seems confused, help them choose the next small step instead of asking for many details.

Bad behavior:
- Do not avoid the question by giving motivational talk first.
- Do not ask multiple questions at once.
- Do not say "according to the context" or "based on the documents."
- Do not mention internal summaries, chunks, sources, or retrieval.

You will produce two fields: "response" (the WhatsApp message to send to the student) and
"updated_session_summary" (a concise updated summary of the current active session).

Rules for updated_session_summary:
- Use the previous current session summary plus the latest student message and your reply.
- Keep only useful admissions context: course interest, fees, eligibility, scholarship, placement concerns, hostel, parent concerns, documents, deadlines, next steps.
- Do not include small talk.
- Do not include information that was not stated or strongly implied.

The response field is the only text the student will see.
The updated_session_summary field is internal and must not be mentioned to the student.
"""




RESOLVE_QUERY_PROMPT = """
You are rewriting a student's WhatsApp message into focused search queries for a college-admissions document retrieval system.

Previous assistant reply for context:
{previous_assistant_message}

Student's latest message:
{query}

If the student's query is in any other language than English, convert it to English first.

First decide: does this message need a document lookup? Greetings ("hi", "hello"), thanks, acknowledgments ("ok", "got it"), or small talk do NOT need retrieval. Questions about fees, courses, eligibility, scholarships, placements, hostel, documents, or deadlines DO need retrieval.

If retrieval is needed, produce 1 to 4 focused search queries. Use exactly 1 for a single-topic question (this is the common case). Only produce more than 1 if the student is genuinely asking about multiple distinct topics or comparing multiple courses/programs in the same message (e.g. "compare CSE and ECE fees and placements" -> separate queries for CSE fees, ECE fees, CSE placements, ECE placements). Resolve pronouns/references using the previous reply. If retrieval is not needed, return an empty list.
"""




RE_QUERY_PROMPT = """
A search for college-admissions documents did not return sufficiently relevant results.

Student's original question:
{original_query}

Previous assistant reply for context:
{previous_assistant_message}

Search queries that were tried and failed to retrieve good matches (one per line):
{failed_queries}

If the student's query is in any other language than English, convert it to English first.

Rewrite each failed query with different phrasing, broader or more specific terms, or synonyms closer to how official documents describe the topic. Return exactly one rewritten query per failed query, in the same order.
"""

settings = get_settings()



@traceable(name="embed_and_retrieve_chunks", run_type="retriever")
async def get_relevant_documents_scored(db, query: str, college_id: int, k: int) -> list[tuple[int, str, float]]:
    start = time.perf_counter()
    try:
        embedder = GoogleGenerativeAIEmbeddings(api_key=settings.gemini_api_key, model=settings.embedding_model, output_dimensionality=settings.vector_size).embed_query(query)
        query_embedding = await embedder.aembed_query(query)
    except Exception as e:
        logger.error("Embedding call failed college_id=%s query=%r error=%s", college_id, query[:200], e, exc_info=True)
        raise # intentionally raised. Caller (agent.py's `retrieve()` node) catches this and falls back to a default SYSTEM_PROMPT so the conversation still continues. Do NOT call build_system_prompt() from anywhere that doesn't have an equivalent fallback in place this function is not safe to call bare.
    try:
        results = await db.execute(select(models.Chunk, models.Chunk.embedding.cosine_distance(query_embedding).label("distance")).where(models.Chunk.college_id == college_id).order_by("distance").limit(k))
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
    result = await db.execute(select(models.Message.content).where(models.Message.college_id == college_id, models.Message.student_id == student_id, models.Message.messager_role == 'assistant').order_by(models.Message.created_at.desc()).limit(1))
    message = result.scalars().first()
    return message or "This is the start of the conversation, no previous message yet."


@traceable(name="build_system_prompt")
async def build_system_prompt(db, query: str, college_id: int, student_id: int, session_id: int, relevant_documents: str, student_summary: str | None = None, session_summary: str | None = None) -> str:
    start = time.perf_counter()
    try:
        college_name_result = db.execute(select(models.College.college_name).where(models.College.college_id == college_id).limit(1))
        college_name = college_name_result.scalars().first()
        college_context_result = db.execute(select(models.College.college_context).where(models.College.college_id == college_id).limit(1))
        college_context = college_context_result.scalars().first()
        previous_assistant_message_result = db.execute(select(models.Message.content).where(models.Message.college_id == college_id, models.Message.student_id == student_id, models.Message.messager_role == 'assistant').order_by(models.Message.created_at.desc()).limit(1))
        previous_assistant_message = previous_assistant_message_result.scalars().first()
    except Exception as e:
        logger.error("build_system_prompt failed college_id=%s student_id=%s session_id=%s error=%s", college_id, student_id, session_id, e, exc_info=True)
        raise  # intentionally raised — caller (agent.py's build_prompt node) must catch this and fall back to a default SYSTEM_PROMPT.
    prompt = SYSTEM_PROMPT.format(
        college_name=college_name,
        student_summary=student_summary or "No long-term student summary yet.",
        session_summary=session_summary or "No current session summary yet.",
        college_context=college_context or "No college-context was added by the college.",
        previous_assistant_message=previous_assistant_message or "This is the start of the conversation, no previous message yet.",
        query=query,
        relevant_documents=relevant_documents,
    )
    logger.debug("System prompt built college_id=%s student_id=%s session_id=%s elapsed_ms=%.0f", college_id, student_id, session_id, (time.perf_counter() - start) * 1000,)
    return prompt