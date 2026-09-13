import logging
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.app.config import get_settings
from backend.app.schemas.models import ReengagementMessage
from backend.app.services.agent_helpers import extract_token_usage

logger = logging.getLogger(__name__)


REENGAGEMENT_PROMPT = """
Decide whether to send a short WhatsApp check-in to a prospective student who has been quiet for about 24 hours.

Student profile:
{student_summary}
Recent session:
{session_summary}
Concerns:
{concerns}
Course interest:
{course_interest}
College strengths:
{key_strengths}

Send only if one specific, relevant strength or next step directly connects to the student's concern or course interest and adds something useful. Otherwise set should_send=false. Never send a generic “still interested?” message. If sending, write 2-3 short, natural sentences, like a staff member remembering the conversation, not a marketing broadcast.
"""



async def generate_reengagement_message(student_summary: str | None, session_summary: str, concerns: list[str] | None, course_interest: str | None, key_strengths: list[str] | None) -> tuple[ReengagementMessage, int, int]:
    """Returns (message, input_tokens, output_tokens) - the token counts are
    for the caller (background_tasks/reengagement_tasks.py) to log via
    cost_service.record_llm_cost, since this function has no db/college_id/
    student_id context of its own to log the cost itself."""
    settings = get_settings()
    llm = ChatGoogleGenerativeAI(model=settings.query_model, temperature=0.4, max_retries=0, api_key=settings.gemini_api_key).with_structured_output(ReengagementMessage, method="json_schema", include_raw=True)
    try:
        result = await llm.ainvoke(REENGAGEMENT_PROMPT.format(student_summary=student_summary or "No long-term summary yet.", session_summary=session_summary, concerns=", ".join(concerns or []) or "None recorded yet.", course_interest=course_interest or "Not yet known", key_strengths=", ".join(key_strengths or []) or "None provided by the college yet."))
        input_tokens, output_tokens = extract_token_usage(result["raw"])
        if result["parsing_error"] is not None:
            raise ValueError(f"Failed to parse LLM output: {result['parsing_error']}")
        return result["parsed"], input_tokens, output_tokens
    except Exception as e:
        logger.warning(f"Failed to generate reengagement message: {e}", exc_info=True)
        return ReengagementMessage(should_send=False, message=None), 0, 0