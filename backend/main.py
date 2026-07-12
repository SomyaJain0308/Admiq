import os, shutil, uuid
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from typing import List


from fastapi import FastAPI, Request, HTTPException, File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from langsmith import traceable


from rag.config import get_settings
from rag.models import (ChatRequest, ChatResponse, HealthResponse, MetricsResponse, ErrorResponse)
from rag.security import SecurityPipeline
from rag.cache import ResponseCache
from rag.monitoring import get_logger, MetricsCollector, RequestTimer
from rag.agent import ProductionAgent
from rag.document_processor import process_uploaded_files
from rag.chunking import chunk_markdown
from rag.vectordb import add_documents



load_dotenv()

logger = get_logger()
security: SecurityPipeline = None
agent: ProductionAgent = None
metrics: MetricsCollector = None
cache: ResponseCache = None

@asynccontextmanager
async def lifespan(app: FastAPI): # Initialize all components on startup
    global security, cache, metrics, agent # Use the variable defined above instead of creating new ones
    settings = get_settings()

    logger.info('Starting Production API...', extra={'extra_data': {
        "environment": settings.app_env,
        "primary_model": settings.primary_model,
        "tracing_enabled": settings.langchain_tracing_v2,
    }})

    security = SecurityPipeline()
    cache = ResponseCache(ttl_seconds=settings.cache_ttl_seconds)
    metrics = MetricsCollector()
    agent = ProductionAgent()

    logger.info("All components initialized. Ready to serve requests.")

    yield # App is running now

    logger.info("Shutting down...", extra={"extra_data": metrics.summary})


# ADDING RATE LIMITING
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="College Chatbot API",
    description="A production-ready chat API with security, caching and observability.",
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
    return JSONResponse(status_code=429, content={
        "error": "Rate limit exceeded",
        "detail": "Too many requests. Please slow down.",
    })


@app.post("/api/chat", response_model=ChatResponse)
@limiter.limit(get_settings().rate_limit)
@traceable(name="chat_endpoint")
async def chat(request: Request, body: ChatRequest):
    
    # Pass user input through the Security Layer
    with RequestTimer() as timer:
        security_notes = []
        is_allowed, cleaned_message, notes = security.check_input(body.message)
        security_notes.extend(notes)
        if not is_allowed:
            logger.warning("Request blocked by security", extra={"extra_data": {
                "reason": notes,
                "thread_id": body.thread_id,
            }})
            metrics.record_request(latency_ms=0, error=True)
            raise HTTPException(
                status_code=400,
                detail="Your message was blocked by our security filters."
            )
        
    # Check if Cached Response is available
    cached_response = cache.get(cleaned_message)
    if cached_response is not None:
        metrics.record_request(latency_ms=0, cache_hit=True)
        logger.info("Cache hit", extra={"extra_data": {
            "thread_id": body.thread_id,
        }})
        return ChatResponse(
            response=cached_response,
            thread_id=body.thread_id,
            model_used="cache",
            cached=True,
            processing_time_ms=0,
        )
    

    # If not cached Invoke langGraph agent. As we set the graphs in agent.py, it will automatically decide which model to use
    try:
        result = agent.invoke(cleaned_message, thread_id=body.thread_id)
    except Exception as e:
        logger.error(f"Agent invocation failed {e}", extra={"extra_data": {
            "thread_id": body.thread_id,
            "error": str(e),
        }})
        metrics.record_request(latency_ms=0, error=True)
        raise HTTPException(
            status_code=500,
            detail="An error occured while processing your request."
        )
    response_text = result["response"]
    model_used = result["model_used"]
    sources = result.get("sources", [])

    # Validating Output of the llm.
    validated_response, output_warnings = security.check_output(response_text)
    security_notes.extend(output_warnings)

    # Cache this Request for future
    cache.set(cleaned_message, validated_response)

    # Log and Record Metrics
    input_tokens = int(len(cleaned_message.split()) * 1.4)
    output_tokens = int(len(validated_response.split()) * 1.4)

    metrics.record_request(
        latency_ms=timer.elapsed_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_hit=False,
    )


    if security_notes:
        logger.info("Security notes", extra={"extra_data": {
            "notes": security_notes,
            "thread_id": body.thread_id,
        }})


    return ChatResponse(
            response=validated_response,
            thread_id=body.thread_id,
            model_used=model_used,
            sources=sources,
            cached=False,
            processing_time_ms=round(timer.elapsed_ms, 2),
        )
    

@app.get("/api/health", response_model=HealthResponse)
async def health():
    settings = get_settings()

    checks = {
        "agent": agent is not None,
        "security": security is not None,
        "cache": cache is not None,
    }

    all_healthy = all(checks.values())

    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        environment=settings.app_env,
        checks=checks,
    )


@app.get("/api/metrics", response_model=MetricsResponse)
async def get_metrics():
    summary = metrics.summary
    return MetricsResponse(**summary)


@app.get("/api/cache/stats")
async def cache_stats():
    return cache.stats

# Get pdfs
UPLOAD_DIR = "pdf_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    saved_paths = []
    for file in files:
        file_id=str(uuid.uuid4())
        temp_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        saved_paths.append(temp_path)

    conversation_results = process_uploaded_files(saved_paths)

    response = []
    for result in conversation_results:
        if not result["success"]:
            response.append({
                "filename": result["filename"],
                "status": "failed",
                "error": result["error"]
            })
            continue

        chunks = chunk_markdown(
            markdown_text=result["markdown"],
            filename=result["filename"],
            extra_metadata={
                "extraction_method": result["method"],
                "quality_score": result["quality_score"],
            },
        )

        add_documents(chunks)

        response.append({
            "filename": result["filename"],
            "status": "success",
            "method": result["method"],
            "quality_score": result["quality_score"],
            "num_chunks": len(chunks),
            "warnings": result["warnings"],
        })
    for path in saved_paths:
        os.remove(path)
    return {"results": response}