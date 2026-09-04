from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from backend.app.database import get_db
from backend.app.models.CollegeStaff_StaffCollege import CollegeStaff
from backend.app.models.Student import Student
from backend.app.models.Message import Message
from backend.app.services.auth_services import verify_college_access
from backend.app.services.csv_export import rows_to_csv_response

router = APIRouter(tags=["Students"], prefix="/router/students")


@router.get("/{college_id}")
async def get_students(
    college_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
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
