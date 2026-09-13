import logging
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.app.config import get_settings
from backend.app.schemas.models import StudentProfileUpdate


logger = logging.getLogger(__name__)


STUDENT_PROFILE_PROMPT = """
Maintain a long-term admissions profile across conversations. Update only from the supplied information.

Existing summary:
{existing_summary}
Existing concerns:
{existing_concerns}
Existing guardian/parent note:
{existing_guardian_involvement}
Existing competing colleges:
{existing_competing_colleges}
Latest session summary:
{session_summary}

Rules:
1. Merge durable admissions context only: course interest, eligibility/scores, fees/scholarships, hostel, concerns, parents/guardians, documents, deadlines, application stage, and next steps. Remove repetition and small talk.
2. Extract current course interest and newly stated academic scores only when explicitly stated. Set interest_signal for this session.
3. Return the FULL concerns list: keep unresolved concerns, remove ones clearly resolved this session, add newly raised concerns. Never invent.
4. Keep guardian/parent involvement unless new information changes it.
5. Return the FULL competing-colleges list, merged and deduplicated.
6. Set dropoff_reason only when this session actually ended with the student going quiet; infer briefly from available context. Otherwise null.
"""


async def generate_profile_update(existing_summary: str | None, session_summary: str, existing_profile_signals: dict | None = None) -> StudentProfileUpdate:
    settings = get_settings()
    existing_profile_signals = existing_profile_signals or {}
    llm = ChatGoogleGenerativeAI(model=settings.query_model, temperature=0, max_retries=0, api_key=settings.gemini_api_key).with_structured_output(StudentProfileUpdate, method="json_schema", include_raw=True)
    try:
        result = await llm.ainvoke(STUDENT_PROFILE_PROMPT.format(existing_summary=existing_summary or "", session_summary=session_summary, existing_concerns=", ".join(existing_profile_signals.get("concerns") or []) or "None recorded yet", existing_guardian_involvement=existing_profile_signals.get("guardian_involvement") or "Not yet known.", existing_competing_colleges=", ".join(existing_profile_signals.get("competing_colleges") or []) or "None mentioned yet."))

        if result["parsing_error"] is not None:
            raise ValueError(f"Failed to parse LLM output: {result['parsing_error']}")
        return result["parsed"]
    except Exception as e:
        logger.warning(f"Failed to generate profile update: {e}", exc_info=True)
        return StudentProfileUpdate(summary=existing_summary or "", course_interest=None, academic_score_updates={}, interest_signal="neutral", concerns=existing_profile_signals.get("concerns") or [], guardian_involvement=existing_profile_signals.get("guardian_involvement"), competing_colleges=existing_profile_signals.get("competing_colleges") or [], dropoff_reason=None)