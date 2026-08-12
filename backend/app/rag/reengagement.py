import logging
from langchain import ChatGoogleGenerativeAI

from backend.app.config import get_settings
from backend.app.schemas.models import ReengagementMessage

logger = logging.getLogger(__name__)


REENGAGEMENT_PROMPT = """
A prospective student contacted a college's WhatsApp admissions assistant but student has gone quiet it's about to be 24 hrs since they last messaged. Decide wheather it's sending a short, casual check-in.

Student's long term summary (may be empty)
{student_summary}

Summary of their most recent conversation:
{session_summary}

Currently known concerns/objections from the student (may be empty):
{concerns}

Currently known course interest (may be unknown):
{course_interest}

The college's key strengths/selling points (staff-provided):
{key_strengths}

Decide:
- Only send something if there's a genuinely relevant, specific angle - ideally a strength that directly addresses one of their concerns, or a strength relevant to their stated course interest that hasn't come up yet in the conversation summary above.
- Do not send a generic "just checking in, still interested?" message with no real context - that's not useful and reads as spam. If nothing specific fits, set should_send to false.
- If sending, keep it short (2-3 sentences), casual and warm, like a real staff member remembered them - not a marketing broadcast. Reference the ONE most relevant strength, ideally tied to their concerm or interest.
"""



async def generate_reengagement_message(student_summary: str | None, session_summary: str, concerns: list[str] | None, course_interest: str | None, key_strengths: list[str] | None) -> ReengagementMessage:
    settings = get_settings()
    llm = ChatGoogleGenerativeAI(model=settings.query_model, temperature=0.4, max_retries=0, api_key=settings.gemini_api_key).with_structured_output(ReengagementMessage, method="json_schema", include_raw=True)
    try:
        result = await llm.ainvoke(REENGAGEMENT_PROMPT.format(student_summary=student_summary or "No long-term summary yet.", session_summary=session_summary, concerns=", ".join(concerns or []) or "None recorded yet.", course_interest=course_interest or "Not yet known", key_strengths=", ".join(key_strengths or []) or "None provided by the college yet."))
        if result["parsing_error"] is not None:
            raise ValueError(f"Failed to parse LLM output: {result['parsing_error']}")
        return result["parsed"]
    except Exception as e:
        logger.warning(f"Failed to generate reengagement message: {e}", exc_info=True)
        return ReengagementMessage(should_send=False, message=None)