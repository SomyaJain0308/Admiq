import logging
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.app.config import get_settings
from backend.app.schemas.models import StudentProfileUpdate


logger = logging.getLogger(__name__)


STUDENT_PROFILE_PROMPT = """
You maintain a long-term profile for a prospective student contacting a college's admissions WhatsApp assistant, across multiple separate conversations over time.

Existing long-term profile (may be empty if this is their first session):
{existing_summary}

Summary of what just happened in their most recent conversation:
{session_summary}

Update the profile: Merge the new summary (durable admissions context only — course interest, eligibility, scholarship/fee concerns, hostel, parent concerns, documents, deadlines, where they are in the journey — no small talk, no repeated facts). Separately extract: their current course of interest if explicitly stated, any new academic scores explicitly stated, and an overall interest signal for this session.
"""


def generate_profile_update(existing_summary: str | None, session_summary: str) -> StudentProfileUpdate:
    settings = get_settings()
    llm = ChatGoogleGenerativeAI(model=settings.query_model, temperature=0, max_retries=0, api_key=settings.gemini_api_key).with_structured_output(StudentProfileUpdate, method="json_schema", include_raw=True)
    try:
        result = llm.invoke(STUDENT_PROFILE_PROMPT.format(existing_summary=existing_summary or "", session_summary=session_summary))
        if result["parsing_error"] is not None:
            raise ValueError(f"Failed to parse LLM output: {result['parsing_error']}")
        return result["parsed"]
    except Exception as e:
        logger.warning(f"Failed to generate profile update: {e}", exc_info=True)
        return StudentProfileUpdate(summary=existing_summary or "", course_interest=None, acedemic_score_updates={}, interest_signal="neutral")