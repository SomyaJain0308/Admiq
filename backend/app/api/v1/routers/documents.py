from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.app.database import get_db
from backend.app.models.Document import Document
from backend.app.models.CollegeStaff_StaffCollege import CollegeStaff
from backend.app.services.auth_services import verify_college_access
from backend.app.services.async_storage_service import upload_file_bytes, delete_file, create_signed_url
from backend.app.services.document_service import async_create_document_row
from backend.app.background_tasks.celery_tasks import process_document_task


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

@router.get("/router/colleges/{college_id}/documents/{document_id}/url")
async def get_document_url(college_id: int, document_id: int, db: Session = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    result = await db.execute(select(Document).where(Document.college_id == college_id, Document.document_id == document_id))
    doc = result.scalars().first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    url = await create_signed_url(doc.storage_path)
    return {"url": url}

@router.delete("/router/colleges/{college_id}/documents/{document_id}", status_code=204)
async def delete_document(college_id: int, document_id: int, db: Session = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    result = await db.execute(select(Document).where(Document.college_id == college_id, Document.document_id == document_id))
    doc = result.scalars().first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    try:
        await delete_file(doc.storage_path)
    except Exception:
        # The DB row (and its chunks, via ON DELETE CASCADE) should still be
        # removed even if the underlying storage object is already gone.
        pass
    await db.delete(doc)
    await db.commit()

@router.post("/router/colleges/{college_id}/documents/{document_id}/retry")
async def retry_document(college_id: int, document_id: int, db: Session = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    result = await db.execute(select(Document).where(Document.college_id == college_id, Document.document_id == document_id))
    doc = result.scalars().first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if doc.document_status != "failed":
        raise HTTPException(status_code=400, detail="Only failed documents can be retried.")
    doc.document_status = "processing"
    doc.error = None
    await db.commit()
    await db.refresh(doc)
    process_document_task.delay(document_id=doc.document_id, college_id=college_id)
    return {"document_id": doc.document_id, "status": doc.document_status}