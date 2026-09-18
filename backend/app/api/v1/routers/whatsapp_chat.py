import logging
import uuid
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from fastapi.responses import PlainTextResponse
from langsmith import traceable
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from backend.app.database import get_db
from backend.app.config import get_settings
from backend.app.rag.security import SecurityPipeline
from backend.app.monitoring.logging_utils import ContextLoggerAdapter
from backend.app.monitoring.timing import RequestTimer
from backend.app.monitoring.api_metrics import STUDENT_TOKEN_BUDGET_REJECTIONS, DUPLICATE_WEBHOOK_DELIVERY, OUTPUT_SECURITY_WARNINGS
from backend.app.rag.agent import Agent
from backend.app.services.tenant_service import get_or_create_student, resolve_college_from_phone_number_id, save_inbound_message, save_assistant_message, flag_low_confidence_query
from backend.app.services.whatsapp_service import send_whatsapp_text_message, send_whatsapp_typing_indicator, send_whatsapp_interactive_message, verify_meta_signature, extract_whatsapp_message_events
from backend.app.services.session_service import get_or_create_active_session, is_session_budget_exceeded, record_session_tokens, update_session_summary, set_session_active_flow
from backend.app.services.cost_service import record_whatsapp_cost
from backend.app.services import eligibility_service


router = APIRouter(prefix="/webhooks/whatsapp", tags=["Whatsapp Chat"])

_module_logger = logging.getLogger(__name__)

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
    processed_count = 0

    for event in events:
        request_id = uuid.uuid4().hex[:12]
        try:
            college_id = await resolve_college_from_phone_number_id(db, event.phone_number_id) # Defined in services/tenant_service.py
        except HTTPException:
            # Now that a single webhook delivery can carry several events
            # (see extract_whatsapp_message_events), one message from an
            # unmapped/unknown number shouldn't 404 the whole request and
            # take every other, valid event in the same batch down with it -
            # skip just this one and keep going. resolve_college_from_
            # phone_number_id already logs the unknown-tenant warning.
            continue
        student = await get_or_create_student(db, college_id=college_id, student_phone=event.student_phone, whatsapp_user_id=event.whatsapp_user_id, student_name=event.student_name) # Defined in services/tenant_service.py
        session = await get_or_create_active_session(db=db, college_id=college_id, student_id=student.student_id) # Defined in services/session_service.py
        logger = ContextLoggerAdapter(_module_logger, {"request_id": request_id})
        logger.extra = {**(logger.extra or {}), "college_id": college_id, "student_id": student.student_id, "session_id": session.session_id}

        # Whatsapp resends ("redelivers") a webhook if we don't respond fast
        # enough - which can happen since the agent/RAG pipeline takes a few
        # seconds. save_inbound_message tells us via is_duplicate whether
        # this whatsapp_message_id was already saved (the common case: the
        # first delivery already finished) so we can skip re-running the
        # agent and re-sending a reply. The IntegrityError catch below is a
        # backstop for the rarer case where two deliveries race each other
        # and both pass the SELECT check before either commits.
        try:
            inbound, is_duplicate = await save_inbound_message(db, college_id=college_id, student_id=student.student_id, whatsapp_message_id=event.whatsapp_message_id, content=event.content, whatsapp_timestamp=event.whatsapp_timestamp, message_type=event.message_type, raw_payload=event.raw_payload, session_id=session.session_id) # Defined in services/tenant_service.py
        except IntegrityError: # Error db sends when unique for something is enabled and it gets violated
            await db.rollback()
            is_duplicate = True
        if is_duplicate:
            DUPLICATE_WEBHOOK_DELIVERY.inc()
            logger.info("Duplicate whatsapp redelivery, skipping", extra={"extra_data": {"whatsapp_message_id": event.whatsapp_message_id}})
            continue

        # Show the "..." typing indicator immediately so the student isn't
        # staring at a static screen while the agent/RAG pipeline (which can
        # take a few seconds) runs below. WhatsApp clears it automatically
        # once send_whatsapp_text_message goes out further down, or after
        # 25s if something goes wrong before we get there - so a failure
        # here is non-fatal and shouldn't block the actual reply.
        typing_result = await send_whatsapp_typing_indicator(phone_number_id=event.phone_number_id, message_id=event.whatsapp_message_id, access_token=get_settings().whatsapp_access_token)
        if not typing_result["ok"]:
            logger.warning("Failed to send Whatsapp typing indicator", extra={"extra_data": {"college_id": college_id, "student_id": student.student_id, "whatsapp_message_id": event.whatsapp_message_id, "meta_response": typing_result}})

        security_notes = []
        # Reset every iteration (this loop can process several events in one
        # webhook delivery) - without this, a security-block/budget-exceeded
        # response, or an agent/eligibility call that raised before
        # assigning it, would leave `result` holding a *previous* event's
        # dict (or unbound on the very first event), and the unguarded
        # `"session_active_flow" in result` check below could then read
        # stale data belonging to a different student's message entirely.
        result = {}

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
                STUDENT_TOKEN_BUDGET_REJECTIONS.inc()
                response_text = "You've reached the message limit for this converstaion. Please wait for 30 minutes and try again. or contact the college directly."
                model_used = "budget_exceeded"
                sources = []

            else:
                # An eligibility check already in progress (StudentSession.
                # active_flow set) or a fresh trigger for one takes over
                # routing here, ahead of the RAG agent - see
                # services/eligibility_service.py for why this is a
                # deterministic state machine rather than an LLM call.
                active_flow_name = (session.active_flow or {}).get("flow")
                in_eligibility_flow = active_flow_name == eligibility_service.FLOW_NAME or eligibility_service.is_trigger(message, event.message_type)

                if in_eligibility_flow:
                    try:
                        # agent is passed through so await_procedure_interest can try a real
                        # RAG lookup instead of always flagging a human - see eligibility_service.py.
                        # Every other step ignores it entirely.
                        result = await eligibility_service.handle_incoming_message(db, college_id=college_id, student=student, session=session, content=message, message_type=event.message_type, agent=agent, request_id=request_id) # Defined in services/eligibility_service.py
                        response_text = result["response"]
                        model_used = result["model_used"]
                        sources = result.get("sources", [])
                        new_session_summary = result.get("updated_session_summary")
                        # Almost always 0/0 (the flow is scripted, not LLM-driven) except for
                        # the RAG-backed procedure-lookup step above, which does spend real
                        # tokens against the session budget just like the agent.invoke() branch below.
                        await record_session_tokens(db, session, result.get("input_tokens", 0), result.get("output_tokens", 0))
                    except Exception as e:
                        logger.error(f"Eligibility flow failed {e}", extra={"extra_data": {"college_id": college_id, "student_id": student.student_id, "error": str(e)}})
                        response_text = "Sorry, something went wrong with the eligibility check. Please try again shortly."
                        model_used = "error"
                        sources = []
                        result = {}
                else:
                    # On success, pass the request to the rag pipeling which will rewrite the query, retrieve documents, determine wheather they r good, if true then send to llm for generation if not rewrite query and the loop continues
                    try:
                        result = await agent.invoke(db, message, college_id=college_id, student_id=student.student_id, request_id=request_id, student_summary=student.summary, session_id=session.session_id, session_summary=session.session_summary) # defined in rag/agent.py
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
            if output_warnings:
                OUTPUT_SECURITY_WARNINGS.inc(len(output_warnings))
            security_notes.extend(output_warnings)
            assistant_msg = await save_assistant_message(db=db, college_id=college_id, student_id=student.student_id, content=response_text, sources=sources, session_id=session.session_id) # Defined in services/tenant_service.py
            if model_used not in ("security_block", "error", "budget_exceeded"):
                if result.get("wants_human_handoff"):
                    await flag_low_confidence_query(db, college_id=college_id, student_id=student.student_id, question_message_id=inbound.message_id, answer_message_id=assistant_msg.message_id, similarity_score=result.get("best_distance")) # Defined in rag/agent.py
            if new_session_summary:
                await update_session_summary(db=db, session=session, session_summary=new_session_summary) # Defined in services/session_service.py
            if "session_active_flow" in result:
                # Only the eligibility flow's result carries this key - persist
                # its next step (or clear it, if the flow just ended) so the
                # *next* inbound message routes correctly. Defined in
                # services/session_service.py.
                await set_session_active_flow(db, session, result["session_active_flow"])

            interactive = result.get("interactive")
            if interactive:
                # response_text above is the flattened version (for the
                # saved transcript/security check) - the actual send uses the
                # real buttons/list. Defined in services/whatsapp_service.py.
                send_result = await send_whatsapp_interactive_message(phone_number_id=event.phone_number_id, to=event.whatsapp_user_id, access_token=get_settings().whatsapp_access_token, interactive=interactive)
            else:
                send_result = await send_whatsapp_text_message(phone_number_id=event.phone_number_id, to=event.whatsapp_user_id, message=response_text, access_token=get_settings().whatsapp_access_token) # Defined in service/whatsapp_service.py
            if not send_result["ok"]:
                logger.error("Failed to send Whatsapp reply", extra={"extra_data": {"college_id": college_id, "student_id": student.student_id, "whatsapp_message_id": event.whatsapp_message_id, "meta_response": send_result}})
            # This is always a free-form reply inside the 24h customer-service window
            # (it's a direct response to the inbound message just processed above), so
            # it's always a "session" conversation for cost purposes.
            await record_whatsapp_cost(db, college_id=college_id, student_id=student.student_id, session_id=session.session_id, category="session", success=send_result["ok"])
            if security_notes:
                logger.info("Security notes", extra={"extra_data": {"notes": security_notes, "college_id": college_id, "student_id": student.student_id}})
        processed_count += 1
    return {"status": "ok", "messages_processed": processed_count}