import hashlib

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from backend.app.database import get_db
from backend.app.models.Document import Document
from backend.app.models.Chunk import Chunk
from backend.app.models.CollegeStaff_StaffCollege import CollegeStaff
from backend.app.services.auth_services import verify_college_access
from backend.app.services.async_storage_service import upload_file_bytes, delete_file_bytes, create_signed_url
from backend.app.services.document_service import async_create_document_row
from backend.app.background_tasks.celery_tasks import process_document_task
from backend.app.schemas.documents import BulkDeleteRequest
from backend.app.monitoring.logging_utils import get_logger

logger = get_logger()

router = APIRouter(tags=["Upload Documents"])

# Maps accepted upload content-types to a short human label, used in error
# messages. Docling (see rag/document_processor.py) can read all three
# natively - PDFs still get the full OCR fallback chain since they're the
# only format that's ever a scan; DOCX/XLSX carry a real text/cell layer
# already so they skip straight to a plain conversion.
ALLOWED_CONTENT_TYPES = {
    "application/pdf": "PDF",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word (.docx)",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel (.xlsx)",
}
MAX_FILE_SIZE_MB = 25


def _unsupported_type_error() -> HTTPException:
    supported = ", ".join(sorted(set(ALLOWED_CONTENT_TYPES.values())))
    return HTTPException(status_code=400, detail=f"Unsupported file type - {supported} are supported right now.")


def _serialize_document(d: Document) -> dict:
    return {
        "document_id": d.document_id,
        "file_name": d.file_name,
        "status": d.document_status,
        "extraction_method": d.extraction_method,
        "quality_score": float(d.quality_score) if d.quality_score is not None else None,
        "num_pages": d.num_pages,
        "error": d.error,
        "category": d.category,
        "created_at": d.created_at.isoformat(),
    }


@router.post("/router/colleges/{college_id}/documents")
async def upload_document(
    college_id: int,
    file: UploadFile = File(...),
    # Optional staff-picked topic label (e.g. "Fees") - purely organizational,
    # doesn't affect retrieval, just makes the documents list browsable.
    category: str | None = Form(None),
    # Set when staff have already seen the duplicate warning below and chose
    # to upload anyway (e.g. it's a legitimately-updated file that happens
    # to hash the same, or two colleges share boilerplate on purpose).
    force: bool = Form(False),
    db: Session = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    uploaded_by = membership.staff_id
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise _unsupported_type_error()
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File too large - max {MAX_FILE_SIZE_MB}MB at a time.")

    category = category.strip() if category and category.strip() else None
    content_hash = hashlib.sha256(file_bytes).hexdigest()

    if not force:
        # Only warn against documents that actually made it into the
        # knowledge base - a failed upload sharing a hash with the file
        # someone's about to retry isn't a "duplicate", it's the fix.
        dup_result = await db.execute(
            select(Document)
            .where(Document.college_id == college_id, Document.content_hash == content_hash, Document.document_status != "failed")
            .order_by(Document.created_at.desc())
            .limit(1)
        )
        existing = dup_result.scalars().first()
        if existing is not None:
            return JSONResponse(
                status_code=409,
                content={
                    "detail": f'This looks like a duplicate of "{existing.file_name}", uploaded {existing.created_at.isoformat()}.',
                    "duplicate": True,
                    "existing_document_id": existing.document_id,
                    "existing_file_name": existing.file_name,
                    "existing_uploaded_at": existing.created_at.isoformat(),
                },
            )

    doc = await async_create_document_row(db, college_id=college_id, file_name=file.filename, storage_path="", uploaded_by=uploaded_by, category=category, content_hash=content_hash)
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
    return [_serialize_document(d) for d in docs]

@router.get("/router/colleges/{college_id}/documents/{document_id}")
async def get_document_status(college_id: int, document_id: int, db: Session = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    result = await db.execute(select(Document).where(Document.college_id == college_id, Document.document_id == document_id))
    doc = result.scalars().first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return _serialize_document(doc)

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


@router.get("/router/colleges/{college_id}/documents/{document_id}/chunks")
async def get_document_chunks(college_id: int, document_id: int, db: Session = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    # Lets staff see exactly what the assistant indexed from a file - not
    # just the pass/fail quality score, but the actual extracted text -
    # so a bad extraction can be caught (and the file replaced) before it
    # ever produces a wrong answer for a student.
    doc_result = await db.execute(select(Document).where(Document.college_id == college_id, Document.document_id == document_id))
    doc = doc_result.scalars().first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    chunks_result = await db.execute(
        select(Chunk).where(Chunk.college_id == college_id, Chunk.document_id == document_id).order_by(Chunk.chunk_index.asc())
    )
    chunks = chunks_result.scalars().all()
    return {
        "document_id": doc.document_id,
        "file_name": doc.file_name,
        "status": doc.document_status,
        "chunks": [{"chunk_id": c.chunk_id, "chunk_index": c.chunk_index, "content": c.chunk_content} for c in chunks],
    }


@router.post("/router/colleges/{college_id}/documents/{document_id}/replace")
async def replace_document(
    college_id: int,
    document_id: int,
    file: UploadFile = File(...),
    category: str | None = Form(None),
    db: Session = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    # Lets staff swap in an updated version of a document without deleting
    # the row and re-uploading from scratch. The document_id stays stable;
    # the old chunks are cleared immediately (not left live until the new
    # ones finish processing) so the assistant is never citing stale content
    # from the file that's about to stop existing.
    result = await db.execute(select(Document).where(Document.college_id == college_id, Document.document_id == document_id))
    doc = result.scalars().first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise _unsupported_type_error()
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File too large - max {MAX_FILE_SIZE_MB}MB at a time.")

    old_storage_path = doc.storage_path
    new_storage_path = f"{college_id}/{doc.document_id}/{file.filename}"
    await upload_file_bytes(new_storage_path, file_bytes, content_type=file.content_type)

    await db.execute(delete(Chunk).where(Chunk.college_id == college_id, Chunk.document_id == document_id))

    doc.file_name = file.filename
    doc.storage_path = new_storage_path
    doc.content_hash = hashlib.sha256(file_bytes).hexdigest()
    if category is not None:
        doc.category = category.strip() or None
    doc.document_status = "processing"
    doc.error = None
    doc.extraction_method = None
    doc.quality_score = None
    doc.num_pages = None
    await db.commit()
    await db.refresh(doc)

    if old_storage_path and old_storage_path != new_storage_path:
        try:
            await delete_file_bytes(old_storage_path)
        except Exception as e:
            logger.error(f"Failed to delete old storage object '{old_storage_path}' after replacing document_id={document_id}: {e}")

    process_document_task.delay(document_id=doc.document_id, college_id=college_id)
    return {"document_id": doc.document_id, "status": doc.document_status}


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
