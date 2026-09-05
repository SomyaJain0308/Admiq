from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from backend.app.database import get_db
from backend.app.models.CollegeStaff_StaffCollege import CollegeStaff, StaffCollege
from backend.app.models.Student import Student
from backend.app.models.Message import Message
from backend.app.models.WhatsappNumber import WhatsAppNumber
from backend.app.services.auth_services import verify_college_access
from backend.app.services.csv_export import rows_to_csv_response
from backend.app.services.tenant_service import save_staff_message
from backend.app.services.whatsapp_service import send_whatsapp_text_message
from backend.app.schemas.students import StudentMessageCreate, StudentMessageResponse, StudentNotesUpdate, StudentAssignUpdate
from backend.app.config import get_settings
from backend.app.monitoring.logging_utils import get_logger

logger = get_logger()

router = APIRouter(tags=["Students"], prefix="/router/students")


@router.get("/{college_id}")
async def get_students(
    college_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=1000),
    search: str | None = Query(default=None, max_length=200),
    db: AsyncSession = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    # Paginated + searched server-side now rather than the frontend fetching
    # every student for the college and filtering client-side - that stopgap
    # was fine at low volume but doesn't scale as a college's student list
    # grows into the hundreds/thousands.
    query = select(Student).where(Student.college_id == college_id)
    count_query = select(func.count()).select_from(Student).where(Student.college_id == college_id)

    if search:
        term = f"%{search.strip()}%"
        search_filter = or_(Student.student_name.ilike(term), Student.student_phone.ilike(term), Student.course_interest.ilike(term))
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    total = (await db.execute(count_query)).scalar_one()

    # Hottest leads first by default - the whole point of lead scoring is
    # surfacing who staff should look at first, so that should be true here
    # too, not just on the dashboard chart.
    query = query.order_by(Student.lead_score.desc()).offset((page - 1) * page_size).limit(page_size)
    students = (await db.execute(query)).scalars().all()

    return {"items": students, "total": total, "page": page, "page_size": page_size}


@router.get("/{college_id}/export")
async def export_students(
    college_id: int,
    search: str | None = Query(default=None, max_length=200),
    db: AsyncSession = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    # Same search filter as the list endpoint, but no pagination - export is
    # meant to hand someone the full matching set for a spreadsheet, not one
    # page of it.
    query = select(Student).where(Student.college_id == college_id)
    if search:
        term = f"%{search.strip()}%"
        query = query.where(or_(Student.student_name.ilike(term), Student.student_phone.ilike(term), Student.course_interest.ilike(term)))
    query = query.order_by(Student.lead_score.desc())
    students = (await db.execute(query)).scalars().all()

    rows = [
        {
            "student_name": s.student_name or "",
            "student_phone": s.student_phone,
            "course_interest": s.course_interest or "",
            "lead_score": s.lead_score,
            "summary": (s.summary or "").replace("\n", " "),
            "created_at": s.created_at.isoformat() if s.created_at else "",
        }
        for s in students
    ]
    columns = ["student_name", "student_phone", "course_interest", "lead_score", "summary", "created_at"]
    return rows_to_csv_response(rows, columns, filename=f"students_college_{college_id}.csv")


@router.get("/{college_id}/{student_id}")
async def get_student(college_id: int, student_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    student_result = await db.execute(select(Student).where(Student.college_id == college_id, Student.student_id == student_id).limit(1))
    student = student_result.scalars().first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@router.get("/view_convo/{college_id}/{student_id}")
async def view_conversation(college_id: int, student_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    convo_result = await db.execute(select(Message).where(Message.college_id == college_id, Message.student_id == student_id).order_by(Message.created_at.asc()))
    convo = convo_result.scalars().all()
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return convo


@router.post("/{college_id}/{student_id}/message", response_model=StudentMessageResponse)
async def message_student(
    college_id: int,
    student_id: int,
    payload: StudentMessageCreate,
    db: AsyncSession = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    # Direct outbound message from a staff member, independent of the
    # low-confidence queue. Reuses the same WhatsApp send + message-save
    # path as the queue's reply endpoint, but without a query_id to resolve,
    # no expiry, and no retrieval-chunk embedding - this is just "say this
    # to the student now," not "teach the assistant this answer."
    staff_id = membership.staff_id
    settings = get_settings()

    student_result = await db.execute(select(Student).where(Student.college_id == college_id, Student.student_id == student_id).limit(1))
    student = student_result.scalars().first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    whatsapp_number_result = await db.execute(select(WhatsAppNumber).where(WhatsAppNumber.college_id == college_id).limit(1))
    whatsapp_number = whatsapp_number_result.scalars().first()
    if not whatsapp_number:
        raise HTTPException(status_code=503, detail="No WhatsApp number configured for this college")

    send_result = await send_whatsapp_text_message(phone_number_id=whatsapp_number.phone_number_id, to=student.whatsapp_user_id, message=payload.content, access_token=settings.whatsapp_access_token)
    if not send_result["ok"]:
        logger.error(f"Failed to deliver staff message to student_id={student_id}")

    # Save it either way, matching the low-confidence reply endpoint's
    # behavior - the message was genuinely sent by staff even if WhatsApp's
    # API call failed, and the frontend surfaces delivery status separately
    # via `delivered` rather than silently dropping the record.
    staff_message = await save_staff_message(db, college_id=college_id, student_id=student_id, staff_id=staff_id, content=payload.content)

    return StudentMessageResponse(
        message_id=staff_message.message_id,
        student_id=staff_message.student_id,
        content=staff_message.content,
        created_at=staff_message.created_at,
        delivered=send_result["ok"],
    )


@router.patch("/{college_id}/{student_id}/notes")
async def update_student_notes(
    college_id: int,
    student_id: int,
    payload: StudentNotesUpdate,
    db: AsyncSession = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    # The column (internal_notes) and its display on StudentDetail already
    # existed - nothing ever wrote to it. This is that write path.
    student_result = await db.execute(select(Student).where(Student.college_id == college_id, Student.student_id == student_id).limit(1))
    student = student_result.scalars().first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    student.internal_notes = payload.internal_notes
    await db.commit()

    return {"student_id": student_id, "internal_notes": student.internal_notes}


@router.patch("/{college_id}/{student_id}/assign")
async def assign_student(
    college_id: int,
    student_id: int,
    payload: StudentAssignUpdate,
    db: AsyncSession = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    # Same situation as internal_notes: assigned_to and its FK to
    # staff_colleges were already in the schema, with nothing to set it.
    student_result = await db.execute(select(Student).where(Student.college_id == college_id, Student.student_id == student_id).limit(1))
    student = student_result.scalars().first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    assigned_staff_name = None
    if payload.assigned_to is not None:
        # Confirm the target staff member is actually part of this college -
        # without this check, one college's staff_id could get assigned a
        # student belonging to a different college, silently violating the
        # multi-tenant separation the rest of the app is careful about.
        staff_membership_result = await db.execute(
            select(StaffCollege)
            .where(StaffCollege.college_id == college_id, StaffCollege.staff_id == payload.assigned_to)
            .options(selectinload(StaffCollege.staff_member))
            .limit(1)
        )
        staff_membership = staff_membership_result.scalars().first()
        if not staff_membership:
            raise HTTPException(status_code=400, detail="That staff member isn't part of this college")
        assigned_staff_name = staff_membership.staff_member.staff_name

    student.assigned_to = payload.assigned_to
    await db.commit()

    return {"student_id": student_id, "assigned_to": student.assigned_to, "assigned_staff_name": assigned_staff_name}
