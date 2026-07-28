import os, tempfile, logging
from backend.backgroundTasks.celery_app import celery_app
from backend.rag.chunking import insert_chunks_to_db
from backend.database.database import SessionLocal
from backend.database import models
from backend.rag import document_processor, chunking
from backend.services.storage_service import download_file_bytes
from backend.services.document_service import update_document_status

from sqlalchemy import select


logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_document_task(self, document_id: int, college_id: int):
    db = SessionLocal()
    tmp_path = None
    try:
        doc = db.execute(select(models.Document).where(models.Document.college_id == college_id, models.Document.document_id == document_id)).scalars().first()
        if doc is None:
            logger.error(f"Document {document_id} not found, aborting task")
            return
        file_bytes = download_file_bytes(doc.storage_path)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        extraction = document_processor.convert_single_pdf(tmp_path)
        if not extraction["success"]:
            update_document_status(db, college_id, document_id, status="failed", error=extraction["error"], extraction_method=extraction["method"], quality_score=extraction["quality_score"], num_pages=extraction["num_pages"])
            return
        contextualized_chunks, vectors = chunking.ingest_markdown(extraction["markdown"], filename=doc.file_name, college_id=college_id)
        insert_chunks_to_db(db, document_id=document_id, college_id=college_id, chunks=contextualized_chunks, vectors=vectors)
        update_document_status(db, college_id, document_id, status="success", extraction_method=extraction["method"], quality_score=extraction["quality_score"], num_pages=extraction["num_pages"])
    except Exception as e:
        logger.error(f"process_document_task failed document_id={document_id} college_id={college_id} error={e}", exc_info=True)
        try:
            update_document_status(db, college_id, document_id, status="failed", error=str(e))
        except Exception:
            pass # DB itself might fail
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        db.close()

