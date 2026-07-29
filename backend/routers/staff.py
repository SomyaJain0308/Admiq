from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.database import get_db
from backend.database.models import CollegeStaff, StaffCollege
from backend.schemas.staff import StaffCreate, StaffLogin, StaffResponse, StaffUpdate



router = APIRouter(tags=["staff"])


@router.get("/router/staff/{college_id}", response_model=list[StaffResponse])
async def get_staff(college_id: int, db: Session = Depends(get_db)):
    staff = db.execute(select(StaffCollege).where(StaffCollege.college_id == college_id)).scalars().all()
    if not staff:
        raise HTTPException(status_code=404, detail="No staff exist yet for this college")
    return [s.staff_member for s in staff]

@router.get("/router/staff/{college_id}/{staff_id}", response_model=StaffResponse)
async def get_staff_by_id(staff_id: int, college_id: int, db: Session = Depends(get_db)):
    existing_staff = db.execute(select(StaffCollege).where(StaffCollege.college_id == college_id, StaffCollege.staff_id == staff_id).limit(1)).scalars().first()
    if not existing_staff:
        raise HTTPException(status_code=404, detail="Staff not Found")
    return existing_staff.staff_member

@router.post("/router/staff/{college_id}", response_model=StaffResponse, status_code=201)
def create_staff(college_id: int, staff: StaffCreate, db: Session = Depends(get_db)):
    existing_staff = db.execute(select(CollegeStaff).where(CollegeStaff.staff_name == staff.staff_name).limit(1)).scalars().first()
    if existing_staff:
        raise HTTPException(status_code=409, detail=f"Staff '{staff.staff_name}' already exists")
    
    existing_email = db.execute(select(CollegeStaff).where(CollegeStaff.staff_email == staff.staff_email).limit(1)).scalars().first()
    if existing_email:
        raise HTTPException(status_code=409, detail=f"Email '{staff.staff_email}' already exists")

    new_staff = CollegeStaff(
        staff_name=staff.staff_name,
        staff_email=staff.staff_email,
        is_active=staff.is_active,
        hashed_password=staff.password
    )
    

    db.add(new_staff)
    db.flush()

    membership = StaffCollege(staff_id=new_staff.staff_id, college_id=college_id)
    db.add(membership)

    db.commit()
    db.refresh(new_staff)

    return new_staff


@router.patch("/router/staff/{college_id}/{staff_id}", response_model=StaffResponse)
async def update_staff(staff_id: int, college_id: int, staff: StaffUpdate, db: Session = Depends(get_db)):
    existing_staff = db.execute(select(StaffCollege).where(StaffCollege.college_id == college_id, StaffCollege.staff_id == staff_id).limit(1)).scalars().first()
    if not existing_staff:
        raise HTTPException(status_code=404, detail="Staff not Found")

    existing_staff = existing_staff.staff_member

    staff = staff.model_dump(exclude_unset=True)
    for field, value in staff.items():
        setattr(existing_staff, field, value)

    db.commit()
    db.refresh(existing_staff)

    return existing_staff


@router.delete("/router/staff/{college_id}/{staff_id}", status_code=204)
async def delete_staff(staff_id: int, college_id: int, db: Session = Depends(get_db)):
    existing_staff = db.execute(select(StaffCollege).where(StaffCollege.college_id == college_id, StaffCollege.staff_id == staff_id).limit(1)).scalars().first()
    if not existing_staff:
        raise HTTPException(status_code=404, detail="Staff not Found")

    db.delete(existing_staff.staff_member)
    db.commit()