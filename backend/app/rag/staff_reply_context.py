from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from backend.app.config import get_settings
from backend.app.schemas.low_confidence import ReconstructedAnswer

RECONSTRUCTED_PROMPT = """
Turn a staff member's answer to an unresolved admissions question into a reusable knowledge-base Q&A.

Recent conversation:
{recent_conversation}
Staff reply:
{staff_reply}

Resolve pronouns/references from the conversation. Write one self-contained question and one concise answer. Use only information in the staff reply; do not infer, embellish, or add facts. The Q&A must stand alone for future retrieval.
"""

def reconstruct_staff_answer(recent_conversation: str, staff_reply: str) -> ReconstructedAnswer:
    settings = get_settings()
    llm = ChatGoogleGenerativeAI(model=settings.query_model, temperature=0, timeout=15, max_retries=0, api_key=settings.gemini_api_key).with_structured_output(ReconstructedAnswer, method="json_schema", include_raw=True)
    result = llm.invoke(RECONSTRUCTED_PROMPT.format(recent_conversation=recent_conversation, staff_reply=staff_reply))
    if result["parsing_error"] is not None:
        raise ValueError(f"structured parse failed: {result['parsing_error']}")
    return result["parsed"]