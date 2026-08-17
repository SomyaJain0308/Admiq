from fastapi import APIRouter, Request, HTTPException, Depends, Query
from fastapi.responses import PlainTextResponse
from langsmith import traceable
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from backend.app.database import get_db
from backend.app.config import get_settings
from backend.app.rag.security import SecurityPipeline
from backend.app.monitoring.logging_utils import get_logger, RequestTimer, STUDENT_TOKEN_BUDGET_REJECTIONS
from backend.app.rag.agent import Agent
from backend.app.services.tenant_service import get_or_create_student, resolve_college_from_phone_number_id, save_inbound_message, save_assistant_message, flag_low_confidence_query
from backend.app.services.whatsapp_service import send_whatsapp_text_message, verify_meta_signature, extract_whatsapp_message_events
from backend.app.services.session_service import get_or_create_active_session, is_session_budget_exceeded, record_session_tokens, update_session_summary


logger = get_logger()

router = APIRouter(prefix="/webhooks/whatsapp", tags=["Whatsapp Chat"])


@router.get("")
async def verify_whatsapp_webhook(hub_verify_token: str | None = Query(None, alias="hub.verify_token"), hub_mode: str | None = Query(None, alias="hub.mode"), hub_challenge: str | None = Query(None, alias="hub.challenge")): # Defined in services/whatsapp_service.py
    if hub_mode == "subscribe" and hub_verify_token == get_settings().whatsapp_verify_token:
        return PlainTextResponse(hub_challenge or "")
    raise HTTPException(status_code=403, detail="Invalid verification token")


@router.post("")
@traceable(name="whatsapp_chat_endpoint")
async def whatsapp_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    security: SecurityPipeline = request.app.state.security
    agent: Agent = request.app.state.agent

    raw_body = await request.body()
    signature_header = request.headers.get("x-hub-signature-256")

    if not verify_meta_signature(raw_body=raw_body, signature_header=signature_header, app_secret=get_settings().meta_app_secret): # Defined in services/whatsapp_service.py
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    payload = await request.json()
    events = extract_whatsapp_message_events(payload) # Defined in services/whatsapp_service.py

    for event in events:
        college_id = await resolve_college_from_phone_number_id(db, event.phone_number_id) # Defined in services/tenant_service.py
        student = await get_or_create_student(db, college_id=college_id, student_phone=event.student_phone, whatsapp_user_id=event.whatsapp_user_id, student_name=event.student_name) # Defined in services/tenant_service.py
        session = await get_or_create_active_session(db=db, college_id=college_id, student_id=student.student_id) # Defined in services/session_service.py

        try: # Sometimes whatsapp resends the message if it does this try/except makes sure there is no duping.
            inbound = await save_inbound_message(db, college_id=college_id, student_id=student.student_id, whatsapp_message_id=event.whatsapp_message_id, content=event.content, whatsapp_timestamp=event.whatsapp_timestamp, message_type=event.message_type, raw_payload=event.raw_payload, session_id=session.session_id) # Defined in services/tenant_service.py
        except IntegrityError: # Error db sends when unique for something is enabled and it gets violated
            await db.rollback()
            logger.info("Duplicate whatsapp redelivery, skipping", extra={"extra_data": {"whatsapp_message_id": event.whatsapp_message_id}})
            continue
        security_notes = []

        with RequestTimer() as timer: # Basic Observability
            # Santize the input and do some basic checking for prompt injection.
            is_allowed, message, notes = security.check_input(event.content) # Defined in rag/security.py
            security_notes.extend(notes)
            new_session_summary = None

            if not is_allowed:
                logger.warning("Incoming WhatsApp message blocked by security", extra={"extra_data": {"reason": notes, "college_id": college_id, "student_id": student.student_id, "whatsapp_message_id": event.whatsapp_message_id,}})
                response_text = "Sorry, I can't help with that message. It is blocked by our security filter. Maybe try and rephrase it?"
                model_used = "security_block"
                sources = []

            elif is_session_budget_exceeded(session, get_settings().session_token_budget): # Rate Limiting (Based on total tokens consumed in the session)
                logger.warning("Session token budget exceeded", extra={"extra_data": {"session_id": session.session_id, "student_id": student.student_id, "college_id": college_id}})
                STUDENT_TOKEN_BUDGET_REJECTIONS.inc() # Defined in rag/monitoring.py again basic observability.
                response_text = "You've reached the message limit for this converstaion. Please wait for 30 minutes and try again. or contact the college directly."
                model_used = "budget_exceeded"
                sources = []

            else:
                # On success, pass the request to the rag pipeling which will rewrite the query, retrieve documents, determine wheather they r good, if true then send to llm for generation if not rewrite query and the loop continues
                try:
                    result = await agent.invoke(db, message, college_id=college_id, student_id=student.student_id, student_summary=student.summary, session_id=session.session_id, session_summary=session.session_summary) # defined in rag/agent.py
                    response_text = result["response"]
                    model_used = result["model_used"]
                    sources = result.get("sources", [])
                    new_session_summary = result.get("updated_session_summary")
                    await record_session_tokens(db, session, result.get("input_tokens", 0), result.get("output_tokens", 0)) # Defined in services/session_services.py
                except Exception as e:
                    logger.error(f"Agent invocation failed {e}", extra={"extra_data": {"college_id": college_id, "student_id": student.student_id, "error": str(e)}})
                    response_text = "Sorry, I am having trouble answering right now. Please try again after 2 minutes."
                    model_used = "error"
                    sources = []
            # Now check the output of the llm make sure it's safe to send to the user
            response_text, output_warnings = security.check_output(response_text) # Defined in rag/security.py
            security_notes.extend(output_warnings)
            assistant_msg = await save_assistant_message(db=db, college_id=college_id, student_id=student.student_id, content=response_text, sources=sources, session_id=session.session_id) # Defined in services/tenant_service.py
            if model_used not in ("security_block", "error", "budget_exceeded"):
                input_tokens = result.get("input_tokens", 0)
                output_tokens = result.get("output_tokens", 0)
                if result.get("wants_human_handoff"):
                    await flag_low_confidence_query(db, college_id=college_id, student_id=student.student_id, question_message_id=inbound.message_id, answer_message_id=assistant_msg.message_id, similarity_score=result.get("best_distance")) # Defined in rag/agent.py
            if new_session_summary:
                await update_session_summary(db=db, session=session, session_summary=new_session_summary) # Defined in services/session_service.py
            send_result = await send_whatsapp_text_message(phone_number_id=event.phone_number_id, to=event.whatsapp_user_id, message=response_text, access_token=get_settings().whatsapp_access_token) # Defined in service/whatsapp_service.py
            if not send_result["ok"]:
                logger.error("Failed to send Whatsapp reply", extra={"extra_data": {"college_id": college_id, "student_id": student.student_id, "whatsapp_message_id": event.whatsapp_message_id, "meta_response": send_result}})
            if security_notes:
                logger.info("Security notes", extra={"extra_data": {"notes": security_notes, "college_id": college_id, "student_id": student.student_id}})
    return {"status": "ok", "messages_processed": len(events)}