import os, tempfile, logging, time
from pathlib import PurePosixPath
from backend.app.rag import chunking
from celery.exceptions import MaxRetriesExceededError
from sqlalchemy import select

from backend.app.background_tasks.celery_app import celery_app
from backend.app.rag.chunking import insert_chunks_to_db
from backend.app.database import SessionLocal
from backend.app.models.Document import Document
from backend.app.rag import document_processor
from backend.app.services.storage_service import download_file_bytes
from backend.app.services.document_service import update_document_status
from backend.app.services.agent_helpers import classify_error
from backend.app.rag.conflict_detection import run_conflict_detection_sync
from backend.app.config import get_settings
from backend.app.monitoring.document_metrics import DOCUMENT_INGESTION_LATENCY, DOCUMENT_INGESTION_STAGE_LATENCY, DOCUMENT_EXTRACTION_METHOD, DOCUMENT_INGESTION_OUTCOME, DOCUMENT_QUALITY_SCORE, DOCUMENT_CHUNKS_CREATED, DOCUMENTS_PAGES_PROCESSED
from backend.app.monitoring.background_tasks_metrics import CELERY_TASK_RETRIES


logger = logging.getLogger(__name__)

RETRYABLE_ERROR_TYPES = {"timeout", "rate_limit", "connection_error"}


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_document_task(self, document_id: int, college_id: int):
    db = SessionLocal()
    tmp_path = None
    task_start = time.perf_counter()
    try:
        doc = db.execute(select(Document).where(Document.college_id == college_id, Document.document_id == document_id)).scalars().first()
        if doc is None:
            logger.error(f"Document {document_id} not found, aborting task")
            return
        file_bytes = download_file_bytes(doc.storage_path)
        # Preserve the original extension (.pdf / .docx / .xlsx) in the temp
        # file name — document_processor.convert_single_document() dispatches
        # on it to decide whether this needs the PDF OCR fallback chain or
        # the plain DOCX/XLSX conversion path.
        suffix = PurePosixPath(doc.file_name).suffix.lower() or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        ocr_start = time.perf_counter()
        extraction = document_processor.convert_single_document(tmp_path)
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
        chunk_rows = insert_chunks_to_db(db, document_id=document_id, college_id=college_id, chunks=contextualized_chunks, vectors=vectors)
        DOCUMENT_INGESTION_STAGE_LATENCY.labels(stage="db_insert").observe(time.perf_counter() - insert_start)

        # Best-effort, and deliberately after insert_chunks_to_db's own
        # commit above - the document's chunks are already safely saved and
        # citable by the assistant by the time this runs, so a flaky LLM
        # call here can only fail to flag a conflict, never lose or delay
        # the ingestion itself. Capped per document (see
        # conflict_max_chunks_per_document) since a large document can
        # produce far more chunks than are worth an LLM call each.
        try:
            settings = get_settings()
            if settings.conflict_detection_enabled and chunk_rows:
                conflict_start = time.perf_counter()
                for chunk_row in chunk_rows[: settings.conflict_max_chunks_per_document]:
                    run_conflict_detection_sync(db, college_id=college_id, new_chunk=chunk_row, document_id=document_id)
                db.commit()
                DOCUMENT_INGESTION_STAGE_LATENCY.labels(stage="conflict_detection").observe(time.perf_counter() - conflict_start)
        except Exception:
            logger.error(f"Conflict detection failed for document_id={document_id} college_id={college_id}", exc_info=True)
            db.rollback()

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

        