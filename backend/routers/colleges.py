from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.database import get_db
from backend.database.models import College
from backend.schemas.colleges import CollegeCreate, CollegeUpdate, CollegeResponse


router = APIRouter(tags=["colleges"])


@router.get("/router/college", response_model=list[CollegeResponse])
async def get_colleges(db: Session = Depends(get_db)):
    colleges = db.execute(select(College)).scalars().all()
    if colleges:  
        return colleges
    else:
        raise HTTPException(status_code=404, detail="No colleges exist yet")


@router.get("/router/college/{college_id}", response_model=CollegeResponse)
async def get_college(college_id: int, db: Session = Depends(get_db)):
    existing_college = db.execute(select(College).where(College.college_id == college_id).limit(1)).scalars().first()
    if existing_college:
        return existing_college
    else:
        raise HTTPException(status_code=404, detail="College not Found")


@router.post("/router/colleges", response_model=CollegeCreate, status_code=201)
def create_college(college: CollegeCreate, db: Session = Depends(get_db)):
    existing_college = db.execute(select(College).where(College.college_name == college.college_name).limit(1)).scalars().first()
    if existing_college:
        raise HTTPException(status_code=409, detail=f"College '{college.college_name}' already exists")
    
    existing_email = db.execute(select(College).where(College.college_email == college.college_email).limit(1)).scalars().first()
    if existing_email:
        raise HTTPException(status_code=409, detail=f"Email '{college.college_email}' already exists")

    existing_phone_number = db.execute(select(College).where(College.college_phone == college.college_phone).limit(1)).scalars().first()
    if existing_phone_number:
        raise HTTPException(status_code=409, detail=f"Phone Number '{college.college_phone}' already exists")


    new_college = College(
        college_name=college.college_name,
        college_phone=college.college_phone,
        college_email=college.college_email,
        college_context=college.college_context
    )
    

    db.add(new_college)
    db.commit()
    db.refresh(new_college)

    return new_college


@router.patch("/router/college/{college_id}", response_model=CollegeResponse)
async def update_college(college_id: int, college: CollegeUpdate, db: Session = Depends(get_db)):
    existing_college = db.execute(select(College).where(College.college_id == college_id).limit(1)).scalars().first()
    if not existing_college:
        raise HTTPException(status_code=404, detail="College not Found")

    college = college.model_dump(exclude_unset=True)
    for field, value in college.items():
        setattr(existing_college, field, value)

    db.commit()
    db.refresh(existing_college)

    return existing_college


@router.delete("/router/college/{college_id}", status_code=204)
async def delete_college(college_id: int, db: Session = Depends(get_db)):
    existing_college = db.execute(select(College).where(College.college_id == college_id).limit(1)).scalars().first()
    if not existing_college:
        raise HTTPException(status_code=404, detail="College not Found")
    db.delete(existing_college)
    db.commit()