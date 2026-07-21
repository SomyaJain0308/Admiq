from contextlib import asynccontextmanager
from dotenv import load_dotenv


from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from langsmith import traceable
from sqlalchemy.orm import Session


from backend.database.database import get_db
from backend.rag.config import get_settings
from backend.rag.security import SecurityPipeline
from backend.rag.monitoring import get_logger, MetricsCollector, RequestTimer
from backend.rag.agent import ProductionAgent
from backend.services.tenant_service import extract_whatsapp_message_events, get_or_create_student, resolve_college_from_phone_number_id, save_inbound_message, save_assistant_message
from backend.schemas.models import (ChatRequest, ChatResponse, HealthResponse, MetricsResponse, ErrorResponse)
from backend.services.webhook_security import verify_meta_signature
from backend.services.whatsapp_service import send_whatsapp_text_message
from backend.services.session_service import get_or_create_active_session, update_session_summary



load_dotenv()

logger = get_logger()
security: SecurityPipeline = None
agent: ProductionAgent = None
metrics: MetricsCollector = None

@asynccontextmanager
async def lifespan(app: FastAPI): # Initialize all components on startup
    global security, metrics, agent # Use the variable defined above instead of creating new ones
    settings = get_settings()

    logger.info('Starting Production API...', extra={'extra_data': {
        "environment": settings.app_env,
        "primary_model": settings.primary_model,
        "tracing_enabled": settings.langchain_tracing_v2,
    }})

    security = SecurityPipeline()
    metrics = MetricsCollector()
    agent = ProductionAgent()

    logger.info("All components initialized. Ready to serve requests.")

    yield # App is running now

    logger.info("Shutting down...", extra={"extra_data": metrics.summary})


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="College Chatbot API",
    description="A production-ready chat API.",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"error": "Rate limit exceeded", "detail": "Too many requests. Please slow down."})

    
@app.get("/webhooks/whatsapp")
async def verify_whatsapp_webhook(
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == get_settings().whatsapp_verify_token:
        return PlainTextResponse(hub_challenge or "")
    
    raise HTTPException(status_code=403, detail="Invalid verification token")


@app.post("/webhooks/whatsapp")
@limiter.limit(get_settings().rate_limit)
@traceable(name="whatsapp_chat_endpoint")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):

    raw_body = await request.body()
    signature_header = request.headers.get("x-hub-signature-256")

    if not verify_meta_signature(raw_body=raw_body, signature_header=signature_header, app_secret=get_settings().meta_app_secret):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    payload = await request.json()
    events = extract_whatsapp_message_events(payload)

    for event in events:
        college_id = resolve_college_from_phone_number_id(db, event.phone_number_id)
        student = get_or_create_student(db, college_id=college_id, student_phone=event.student_phone, whatsapp_user_id=event.whatsapp_user_id, student_name=event.student_name)
        session = get_or_create_active_session(db=db, college_id=college_id, student_id=student.student_id)
        save_inbound_message(db, college_id=college_id, student_id=student.student_id, whatsapp_message_id=event.whatsapp_message_id, content=event.content, whatsapp_timestamp=event.whatsapp_timestamp, message_type=event.message_type, raw_payload=event.raw_payload, session_id=session.session_id)
        thread_id = f"whatsapp:{college_id}:{student.student_id}"
        security_notes = []
        
        # Pass user input through the Security Layer
        with RequestTimer() as timer:
            is_allowed, cleaned_message, notes = security.check_input(event.content)
            security_notes.extend(notes)
            new_session_summary = None

            if not is_allowed:
                logger.warning("Incoming WhatsApp message blocked by security", extra={"extra_data": {"reason": notes, "college_id": college_id, "student_id": student.student_id, "whatsapp_message_id": event.whatsapp_message_id,}})
                metrics.record_request(latency_ms=timer.elapsed_ms,error=True)
                response_text = "Sorry, I can't help with that message. It is blocked by our security filter."
                model_used = "security_block"
                sources = []
            else:
                try:
                    result = agent.invoke(db, cleaned_message, college_id=college_id, thread_id=thread_id, student_summary=student.summary, session_summary=session.session_summary)
                    response_text = result["response"]
                    model_used = result["model_used"]
                    sources = result.get("sources", [])
                    new_session_summary = result.get("updated_session_summary")
                except Exception as e:
                    logger.error(f"Agent invocation failed {e}", extra={"extra_data": {"thread_id": thread_id, "college_id": college_id, "student_id": student.student_id, "error": str(e)}})
                    metrics.record_request(latency_ms=timer.elapsed_ms, error=True)
                    response_text = "Sorry, I am having trouble answering right now. Please try again in a moment."
                    model_used = "error"
                    sources = []

            response_text, output_warnings = security.check_output(response_text)
            security_notes.extend(output_warnings)

            if model_used not in ("security_block", "error"):
                input_tokens = int(len(cleaned_message.split()) * 1.4)
                output_tokens = int(len(response_text.split()) * 1.4)
                metrics.record_request(latency_ms=timer.elapsed_ms, input_tokens=input_tokens, output_tokens=output_tokens)

            if new_session_summary:
                update_session_summary(db=db, session=session, session_summary=new_session_summary)
            save_assistant_message(db=db, college_id=college_id, student_id=student.student_id, content=response_text, sources=sources, session_id=session.session_id)
            send_result = send_whatsapp_text_message(phone_number_id=event.phone_number_id, to=event.whatsapp_user_id, message=response_text, access_token=get_settings().whatsapp_access_token)
            if not send_result["ok"]:
                logger.error("Failed to send Whatsapp reply", extra={"extra_data": {
                    "college_id": college_id,
                    "student_id": student.student_id,
                    "whatsapp_message_id": event.whatsapp_message_id,
                    "meta_response": send_result,
                }})
            if security_notes:
                logger.info("Security notes", extra={"extra_data": {"notes": security_notes, "thread_id": thread_id, "college_id": college_id, "student_id": student.student_id}})
    return {"status": "ok", "messages_processed": len(events)}

    

@app.get("/api/health", response_model=HealthResponse)
async def health():
    settings = get_settings()
    checks = {"agent": agent is not None, "security": security is not None}
    all_healthy = all(checks.values())
    return HealthResponse(status="healthy" if all_healthy else "degraded", environment=settings.app_env, checks=checks)


@app.get("/api/metrics", response_model=MetricsResponse)
async def get_metrics():
    summary = metrics.summary
    return MetricsResponse(**summary)
