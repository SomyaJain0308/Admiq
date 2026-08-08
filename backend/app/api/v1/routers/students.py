from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.database import get_db
from backend.app.models.Student import Student
from backend.app.models.Message import Message

router = APIRouter(tags=["Students"], prefix="/router/students")


@router.get("{college_id}")
async def get_students(college_id: int, db: AsyncSession = Depends(get_db)):
    students_result = await db.execute(select(Student).where(Student.college_id == college_id))
    students = students_result.scalars().all()
    if not students:
        raise HTTPException(status_code=404, detail="No students found for this college")
    return students


@router.get("{college_id}/{student_id}")
async def get_student(college_id: int, student_id: int, db: AsyncSession = Depends(get_db)):
    student_result = await db.execute(select(Student).where(Student.college_id == college_id, Student.id == student_id).limit(1))
    student = student_result.scalars().first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@router.get("/view_convo/{college_id}/{student_id}")
async def view_conversation(college_id: int, student_id: int, db: AsyncSession = Depends(get_db)):
    convo_result = await db.execute(select(Message).where(Message.college_id == college_id, Message.student_id == student_id).order_by(Message.created_at.asc()))
    convo = convo_result.scalars().all()
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return convo