import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from backend.app.config import get_settings
from backend.app.schemas.models import StudentProfileSummary


logger = logging.getLogger(__name__)


STUDENT_PROFILE_PROMPT = """
You maintain a long-term profile summary for a prospective student contacting a college's admissions WhatsApp assistant, across multiple separate conversations over time.

Existing long-term profile (may be empty if this is their first session):
{existing_summary}

Summary of what just happened in their most recent conversation:
{session_summary}

Merge the new session into the existing profile. Keep only durable, useful admissions context: course interest, eligibility details, scholarship/fee concerns, hostel interest, parent concerns, documents submitted or still needed, deadlines discussed, and where they are in the admissions journey. Do not include small talk. Do not repeat the same fact twice. If the new session doesn't add anything durable, return the existing profile unchanged. Keep it concise — a few sentences, not a transcript.
"""


def merge_student_profile(existing_summary: str | None, session_summary: str) -> str:
    settings = get_settings()
    llm = ChatGoogleGenerativeAI(models=settings.query_model, temperature=0, max_retries=0, api_key=settings.gemini_api_key).with_structured_output(StudentProfileSummary, method="json_schema", include_raw=True)
    try:
        result = llm.invoke(STUDENT_PROFILE_PROMPT.format(existing_summary=existing_summary or "", session_summary=session_summary))
        if result["parsing_error"] is not None:
            raise ValueError(f"Failed to parse LLM output: {result['parsing_error']}")
        return result["parsed"].summary
    except Exception as e:
        logger.warning(f"Failed to merge student profile: {e}", exc_info=True)
        return existing_summary or ""