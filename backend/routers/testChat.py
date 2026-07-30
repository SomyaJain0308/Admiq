from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import uuid, time

from backend.database.database import get_db
from backend.rag.config import get_settings
from backend.rag.monitoring import STUDENT_TOKEN_BUDGET_REJECTIONS
from backend.services.tenant_service import flag_low_confidence_query, get_or_create_student, save_assistant_message, save_inbound_message
from backend.services.session_service import get_or_create_active_session, is_session_budget_exceeded, record_session_tokens, update_session_summary
from backend.schemas.models import ChatTestRequest, ChatTestResponse
from backend.main import security, agent


router = APIRouter(tags=["Chat (Test)"])


@router.post("/router/test/chat", response_model=ChatTestResponse)
async def test_chat(payload: ChatTestRequest, db: Session = Depends(get_db)):
    student = get_or_create_student(db, college_id=payload.college_id, student_phone=payload.student_phone, whatsapp_user_id=payload.student_phone, student_name=payload.student_name)
    session = get_or_create_active_session(db=db, college_id=payload.college_id, student_id=student.student_id)

    save_inbound_message(db, college_id=payload.college_id, student_id=student.student_id, whatsapp_message_id=f"test-{uuid.uuid4()}", content=payload.message, whatsapp_timestamp=time.thread_time, message_type="text", raw_payload={}, session_id=session.session_id)
    is_allowed, message, notes = security.check_input(payload.message)
    new_session_summary = None

    if not is_allowed:
        response_text, model_used, sources, wants_human_handoff, best_distance = "Sorry, I can't help with that message. It is blocked by our security filter.", "security_block", [], False, None
    elif is_session_budget_exceeded(session, get_settings().session_token_budget):
        STUDENT_TOKEN_BUDGET_REJECTIONS.inc()
        response_text, model_used, sources, wants_human_handoff, best_distance = "You've reached the message limit for this conversation. Try again after 30 minutes.", "budget_exceeded", [], False, None
    else:
        result = agent.invoke(db, message, college_id=payload.college_id, student_id=student.student_id, student_summary=student.summary, session_id=session.session_id, session_summary=session.session_summary)
        response_text, model_used, sources, wants_human_handoff, best_distance, new_session_summary = result["response"], result["model_used"], result.get("sources", []), result.get("wants_human_handoff", False), result.get("best_distance"), result.get("updated_session_summary")
        record_session_tokens(db, session, result.get("input_tokens", 0), result.get("output_tokens", 0))
    response_text, _ = security.check_output(response_text)
    assistant_msg = save_assistant_message(db, college_id=payload.college_id, student_id=student.student_id, content=response_text, sources=sources, session_id=session.session_id)

    if model_used not in ["security_block", "error", "budget_exceeded"] and wants_human_handoff:
        flag_low_confidence_query(db, college_id=payload.college_id, student_id=student.student_id, question_message_id=None, answer_message_id=assistant_msg.message_id, similarity_score=best_distance)
    if new_session_summary:
        update_session_summary(db=db, session=session, session_summary=new_session_summary)
    return ChatTestResponse(response=response_text, model_used=model_used, sources=sources, wants_human_handoff=wants_human_handoff, best_distance=best_distance, session_id=session.session_id, student_id=student.student_id)