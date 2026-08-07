from sqlalchemy import select

from backend.app.models.Document import Document


def create_document_row(db, college_id: int, file_name: str, storage_path: str, uploaded_by: int) -> Document: # Used by celery_tasks.py
    doc = Document(college_id=college_id, file_name=file_name, storage_path=storage_path, uploaded_by=uploaded_by, document_status="processing")
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


async def async_create_document_row(db, college_id: int, file_name: str, storage_path: str, uploaded_by: int) -> Document: # Used by documents.py
    doc = Document(college_id=college_id, file_name=file_name, storage_path=storage_path, uploaded_by=uploaded_by, document_status="processing")
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


def update_document_status(db, college_id: int, document_id: int, status: str, extraction_method: str | None = None, quality_score: float | None = None, num_pages: int | None = None, error: str | None = None) -> Document | None:
    doc = db.execute(select(Document).where(Document.college_id == college_id, Document.document_id == document_id).limit(1)).scalars().first()
    if doc is None:
        return None
    doc.document_status = status
    if extraction_method is not None:
        doc.extraction_method = extraction_method
    if quality_score is not None:
        doc.quality_score = quality_score
    if num_pages is not None:
        doc.num_pages = num_pages
    if error is not None:
        doc.error = error
    db.commit()
    db.refresh(doc)
    return doc
