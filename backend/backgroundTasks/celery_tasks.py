import os, tempfile, logging, time
from celery.exceptions import MaxRetriesExceededError

from backend.backgroundTasks.celery_app import celery_app
from backend.rag.chunking import insert_chunks_to_db
from backend.database.database import SessionLocal
from backend.database import models
from backend.rag import document_processor, chunking
from backend.services.storage_service import download_file_bytes
from backend.services.document_service import update_document_status
from backend.services.agent_helpers import classify_error
from backend.rag.monitoring import DOCUMENT_INGESTION_LATENCY, DOCUMENT_INGESTION_STAGE_LATENCY, DOCUMENT_EXTRACTION_METHOD, DOCUMENT_INGESTION_OUTCOME, DOCUMENT_QUALITY_SCORE, DOCUMENT_CHUNKS_CREATED, DOCUMENTS_PAGES_PROCESSED, CELERY_TASK_RETRIES

from sqlalchemy import select



logger = logging.getLogger(__name__)

RETRYABLE_ERROR_TYPES = {"timeout", "rate_limit", "connection_error"}


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_document_task(self, document_id: int, college_id: int):
    db = SessionLocal()
    tmp_path = None
    task_start = time.perf_counter()
    try:
        doc = db.execute(select(models.Document).where(models.Document.college_id == college_id, models.Document.document_id == document_id)).scalars().first()
        if doc is None:
            logger.error(f"Document {document_id} not found, aborting task")
            return
        file_bytes = download_file_bytes(doc.storage_path)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        ocr_start = time.perf_counter()
        extraction = document_processor.convert_single_pdf(tmp_path)
        DOCUMENT_INGESTION_STAGE_LATENCY.labels(stage="ocr_extraction").observe(time.perf_counter() - ocr_start)
        DOCUMENT_EXTRACTION_METHOD.labels(method=extraction["method"] or "unknown").inc()
        if extraction.get("quality_score") is not None:
            DOCUMENT_QUALITY_SCORE.observe(extraction["quality_score"])
        if extraction.get("num_pages") is not None:
            DOCUMENTS_PAGES_PROCESSED.observe(extraction["num_pages"])

        if not extraction["success"]:
            update_document_status(db, college_id, document_id, status="failed", error=extraction["error"], extraction_method=extraction["method"], quality_score=extraction["quality_score"], num_pages=extraction["num_pages"])
            DOCUMENT_INGESTION_OUTCOME.labels(outcome="failed", error_type=extraction["error"]).inc()
            return

        ingest_start = time.perf_counter()
        contextualized_chunks, vectors = chunking.ingest_markdown(extraction["markdown"], filename=doc.file_name, college_id=college_id)
        DOCUMENT_INGESTION_STAGE_LATENCY.labels(stage="chunk_contextualize_embed").observe(time.perf_counter() - ingest_start)
        DOCUMENT_CHUNKS_CREATED.observe(len(contextualized_chunks))

        insert_start = time.perf_counter()
        insert_chunks_to_db(db, document_id=document_id, college_id=college_id, chunks=contextualized_chunks, vectors=vectors)
        DOCUMENT_INGESTION_STAGE_LATENCY.labels(stage="db_insert").observe(time.perf_counter() - insert_start)

        update_document_status(db, college_id, document_id, status="success", extraction_method=extraction["method"], quality_score=extraction["quality_score"], num_pages=extraction["num_pages"])
        DOCUMENT_INGESTION_OUTCOME.labels(outcome="success", error_type="").inc()
    except Exception as e:
        error_type = classify_error(e)
        logger.error(f"process_document_task failed document_id={document_id} college_id={college_id} error={e}", exc_info=True)
        db.rollback()
        if error_type in RETRYABLE_ERROR_TYPES:
            CELERY_TASK_RETRIES.labels(task_name="process_document_task", error_type=error_type).inc()
            try:
                raise self.retry(exc=e, countdown=60)
            except MaxRetriesExceededError:
                logger.error(f"process_document_status exhausted retries document_id={document_id}")
                DOCUMENT_INGESTION_OUTCOME.labels(outcome="failed", error_type=f"{error_type}_exhausted_retries").inc()
                try:
                    update_document_status(db, college_id, document_id, status="failed", error=str(e))
                except Exception:
                    pass # DB itself might fail
        else:
            DOCUMENT_INGESTION_OUTCOME.labels(outcome="failed", error_type=error_type).inc()
            try:
                update_document_status(db, college_id, document_id, status="failed", error=str(e))
            except Exception:
                pass # DB itself might fail
    finally:
        DOCUMENT_INGESTION_LATENCY.observe(time.perf_counter() - task_start)
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        db.close()

