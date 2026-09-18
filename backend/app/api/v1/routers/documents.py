from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.app.database import get_db
from backend.app.models.Document import Document
from backend.app.models.CollegeStaff_StaffCollege import CollegeStaff
from backend.app.services.auth_services import verify_college_access
from backend.app.services.async_storage_service import upload_file_bytes, delete_file_bytes, create_signed_url
from backend.app.services.document_service import async_create_document_row
from backend.app.background_tasks.celery_tasks import process_document_task
from backend.app.schemas.documents import BulkDeleteRequest
from backend.app.monitoring.logging_utils import get_logger

logger = get_logger()

router = APIRouter(tags=["Upload Documents"])

ALLOWED_CONTENT_TYPES = {"application/pdf"}
MAX_FILE_SIZE_MB = 25

@router.post("/router/colleges/{college_id}/documents")
async def upload_document(college_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    uploaded_by = membership.staff_id
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF files are supported right now.")
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File too large - max {MAX_FILE_SIZE_MB}MB at a time.")
    doc = await async_create_document_row(db, college_id=college_id, file_name=file.filename, storage_path="", uploaded_by=uploaded_by)
    storage_path = f"{college_id}/{doc.document_id}/{file.filename}"
    await upload_file_bytes(storage_path, file_bytes, content_type=file.content_type)
    doc.storage_path = storage_path
    await db.commit()
    await db.refresh(doc)
    process_document_task.delay(document_id = doc.document_id, college_id=college_id)
    return {"document_id": doc.document_id, "status": doc.document_status}

@router.get("/router/colleges/{college_id}/documents")
async def list_documents(college_id: int, db: Session = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    result = await db.execute(select(Document).where(Document.college_id == college_id).order_by(Document.created_at.desc()))
    docs = result.scalars().all()
    return [{"document_id": d.document_id, "file_name": d.file_name, "status": d.document_status, "extraction_method": d.extraction_method, "quality_score": float(d.quality_score) if d.quality_score is not None else None, "num_pages": d.num_pages, "error": d.error, "created_at": d.created_at.isoformat()} for d in docs]

@router.get("/router/colleges/{college_id}/documents/{document_id}")
async def get_document_status(college_id: int, document_id: int, db: Session = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    result = await db.execute(select(Document).where(Document.college_id == college_id, Document.document_id == document_id))
    doc = result.scalars().first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"document_id": doc.document_id, "file_name": doc.file_name, "status": doc.document_status, "extraction_method": doc.extraction_method, "quality_score": float(doc.quality_score) if doc.quality_score is not None else None, "num_pages": doc.num_pages, "error": doc.error, "created_at": doc.created_at.isoformat()}

@router.get("/router/colleges/{college_id}/documents/{document_id}/view-url")
async def get_document_view_url(college_id: int, document_id: int, db: Session = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    result = await db.execute(select(Document).where(Document.college_id == college_id, Document.document_id == document_id))
    doc = result.scalars().first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if not doc.storage_path:
        # Row exists but the upload never finished writing storage_path
        # (e.g. crashed between async_create_document_row and the storage
        # upload completing) - nothing to sign a URL for.
        raise HTTPException(status_code=404, detail="This file isn't available in storage.")
    url = await create_signed_url(doc.storage_path)
    return {"url": url}


@router.post("/router/colleges/{college_id}/documents/{document_id}/retry")
async def retry_document(college_id: int, document_id: int, db: Session = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    result = await db.execute(select(Document).where(Document.college_id == college_id, Document.document_id == document_id))
    doc = result.scalars().first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if doc.document_status != "failed":
        raise HTTPException(status_code=400, detail="Only failed documents can be retried.")
    if not doc.storage_path:
        # Nothing in storage to re-process (e.g. crashed before the upload
        # finished writing storage_path) - re-uploading is the only option.
        raise HTTPException(status_code=400, detail="The original file isn't available - please re-upload it.")
    # Reset directly rather than via update_document_status: that helper only
    # overwrites fields it's given, and we specifically need error to go back
    # to NULL (a stale error message sitting next to a fresh "processing"
    # status would look like a bug) so the row goes back to a clean pending
    # state.
    doc.document_status = "processing"
    doc.error = None
    await db.commit()
    await db.refresh(doc)
    process_document_task.delay(document_id=doc.document_id, college_id=college_id)
    return {"document_id": doc.document_id, "status": doc.document_status}


@router.post("/router/colleges/{college_id}/documents/bulk-delete")
async def bulk_delete_documents(college_id: int, payload: BulkDeleteRequest, db: Session = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    result = await db.execute(select(Document).where(Document.college_id == college_id, Document.document_id.in_(payload.document_ids)))
    docs = result.scalars().all()
    found_ids = {d.document_id for d in docs}
    not_found_ids = [i for i in payload.document_ids if i not in found_ids]
    storage_paths = [d.storage_path for d in docs if d.storage_path]

    # Same reasoning as the single-document delete below: the DB delete (and
    # its cascading chunk delete) is the part that actually stops the
    # assistant from citing these documents, so it happens as one
    # transaction first. Storage cleanup is best-effort afterwards - a
    # partial storage failure should never leave any of these rows
    # half-deleted or still feeding wrong answers.
    for doc in docs:
        await db.delete(doc)
    await db.commit()

    for storage_path in storage_paths:
        try:
            await delete_file_bytes(storage_path)
        except Exception as e:
            logger.error(f"Failed to delete storage object '{storage_path}' during bulk delete for college_id={college_id}: {e}")

    return {
        "deleted_ids": sorted(found_ids),
        "not_found_ids": not_found_ids,
    }


@router.delete("/router/colleges/{college_id}/documents/{document_id}", status_code=204)
async def delete_document(college_id: int, document_id: int, db: Session = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    result = await db.execute(select(Document).where(Document.college_id == college_id, Document.document_id == document_id))
    doc = result.scalars().first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    storage_path = doc.storage_path
    await db.delete(doc)
    await db.commit()
    # The FK from chunks.document_id is ondelete="CASCADE", so the delete
    # above already removed every chunk of this document from the retrieval
    # index - that's the part that actually stops the assistant from citing
    # it. Deleting the underlying file from storage is best-effort cleanup
    # after that: it runs after the commit (not before, and not in the same
    # transaction) so a storage hiccup can never leave the DB row/chunks
    # half-deleted or block staff from retiring a document from the
    # knowledge base. A leftover blob in the bucket is just an orphaned
    # file; a stuck DB row still feeding wrong answers is the real harm.
    if storage_path:
        try:
            await delete_file_bytes(storage_path)
        except Exception as e:
            logger.error(f"Failed to delete storage object '{storage_path}' for document_id={document_id}: {e}")