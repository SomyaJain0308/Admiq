import logging
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.app.config import get_settings
from backend.app.schemas.models import StudentProfileUpdate


logger = logging.getLogger(__name__)


STUDENT_PROFILE_PROMPT = """
You maintain a long-term profile for a prospective student contacting a college's admissions WhatsApp assistant, across multiple separate conversations over time.

Existing long-term profile (may be empty if this is their first session):
{existing_summary}

Existing concerns/objections (may be empty):
{existing_concerns}

Exostomg guardian/parent involvement note (may be unknown):
{existing_guardian_involvement}

Existing competing colleges mentioned (may be empty):
{existing_competing_colleges}

Summary of what just happened in their most recent conversation:
{session_summary}

Update the profile:
1. Merge the new summary (durable admissions context only — course interest, eligibility, scholarship/fee concerns, hostel, parent concerns, documents, deadlines, where they are in the journey — no small talk, no repeated facts).
2. Separately extract: their current course of interest if explicitly stated, any new academic scores explicitly stated, and an overall interest signal for this session.
3. Update concerns: return the FULL current list, carrying forward unresolved concerns, dropping any resolved this session, and adding new ones raised. Do not invent concerns.
4. Update guardian_involvement: only change it if this session revealed new/changed information; otherwise keep the existing note as-is (or null if never mentioned).
5. Update competing_colleges: return the FULL current list, merging in any newly mentioned colleges and deduplicating.
6. Set dropoff_reason: only if THIS session ended with the student going quiet / not responding to a follow-up, giving a short inferred reason. Null if the session ended normally, or if a prior drop-off was resolved this session.
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