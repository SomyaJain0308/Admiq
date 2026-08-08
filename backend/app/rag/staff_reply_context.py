from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from backend.app.config import get_settings
from backend.app.schemas.low_confidence import ReconstructedAnswer

RECONSTRUCTED_PROMPT = """
A student asked a question that the assistant couldn't answer confidently. A staff member has now provided the real answer. Your job is to turn this into a clean, self-contained Q&A pair for a knowledge base — future students may ask similar questions and this should be retrievable on its own, without needing the original conversation.

Recent conversation leading up to the flagged question:
{recent_conversation}

Staff member's reply:
{staff_reply}

Resolve any pronouns or references using the conversation above. Write a single, clear, self-contained question capturing what was actually being asked, and a concise answer based on the staff reply. Do not add information the staff member didn't provide.
"""

def reconstruct_staff_answer(recent_conversation: str, staff_reply: str) -> ReconstructedAnswer:
    settings = get_settings()
    llm = ChatGoogleGenerativeAI(model=settings.query_model, temperature=0, timeout=15, max_retries=0, api_key=settings.gemini_api_key)
    result = llm.invoke(RECONSTRUCTED_PROMPT.format(recent_conversation=recent_conversation, staff_reply=staff_reply))
    if result["parsing_error"] is not None:
        raise ValueError(f"structured parse failed: {result['parsing_error']}")
    return result["parsed"]