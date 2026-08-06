from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.database.database import get_db
from backend.app.models.models import CollegeStaff, StaffCollege, College
from backend.app.schemas.staff import StaffCreate, StaffLogin, StaffResponse, StaffUpdate


router = APIRouter(tags=["staff"])


@router.get("/router/staff/{college_id}", response_model=list[StaffResponse])
async def get_staff(college_id: int, db: AsyncSession = Depends(get_db)):
    college_exists = await db.execute(select(College.college_id).where(College.college_id == college_id).limit(1))
    if not college_exists.scalar():
        raise HTTPException(status_code=404, detail="College not found")
    staff_results = await db.execute(select(StaffCollege).where(StaffCollege.college_id == college_id).options(selectinload(StaffCollege.staff_member)))
    staff = staff_results.scalars().all()
    if not staff:
        raise HTTPException(status_code=404, detail="No staff exist yet for this college")
    return [s.staff_member for s in staff]

@router.get("/router/staff/{college_id}/{staff_id}", response_model=StaffResponse)
async def get_staff_by_id(staff_id: int, college_id: int, db: AsyncSession = Depends(get_db)):
    college_exists = await db.execute(select(College.college_id).where(College.college_id == college_id).limit(1))
    if not college_exists.scalar():
        raise HTTPException(status_code=404, detail="College not found")
    existing_staff_result = await db.execute(select(StaffCollege).where(StaffCollege.college_id == college_id, StaffCollege.staff_id == staff_id).options(selectinload(StaffCollege.staff_member)).limit(1))
    existing_staff = existing_staff_result.scalars().first()
    if not existing_staff:
        raise HTTPException(status_code=404, detail="Staff not Found")
    return existing_staff.staff_member


@router.post("/router/staff/{college_id}", response_model=StaffResponse, status_code=201)
async def create_staff(college_id: int, staff: StaffCreate, db: AsyncSession = Depends(get_db)):
    college_exists = await db.execute(select(College.college_id).where(College.college_id == college_id).limit(1))
    if not college_exists.scalar():
        raise HTTPException(status_code=404, detail="College not found")

    existing_staff_result = await db.execute(select(CollegeStaff).where(CollegeStaff.staff_email == staff.staff_email).limit(1))
    existing_staff = existing_staff_result.scalars().first()

    if existing_staff: # We can't do both the db calls in one it's intentional.
        membership_result = await db.execute(select(StaffCollege).where(StaffCollege.college_id == college_id, StaffCollege.staff_id == existing_staff.staff_id).limit(1))
        if membership_result.scalars().first():
            raise HTTPException(status_code=409, detail=f"'{staff.staff_email}' is already staff at this college")

        membership = StaffCollege(staff_id=existing_staff.staff_id, college_id=college_id)
        db.add(membership)
        await db.commit()
        await db.refresh(existing_staff)
        return existing_staff

    new_staff = CollegeStaff(staff_name=staff.staff_name, staff_email=staff.staff_email, is_active=staff.is_active, hashed_password=staff.password)
    db.add(new_staff)
    await db.flush()

    membership = StaffCollege(staff_id=new_staff.staff_id, college_id=college_id)
    db.add(membership)
    await db.commit()
    await db.refresh(new_staff)
    return new_staff


@router.patch("/router/staff/{college_id}/{staff_id}", response_model=StaffResponse)
async def update_staff(staff_id: int, college_id: int, staff: StaffUpdate, db: AsyncSession = Depends(get_db)):
    college_exists = await db.execute(select(College.college_id).where(College.college_id == college_id).limit(1))
    if not college_exists.scalar():
        raise HTTPException(status_code=404, detail="College not found")

    existing_staff_result = await db.execute(
        select(StaffCollege)
        .where(StaffCollege.college_id == college_id, StaffCollege.staff_id == staff_id)
        .options(selectinload(StaffCollege.staff_member))
        .limit(1)
    )
    membership = existing_staff_result.scalars().first()
    if not membership:
        raise HTTPException(status_code=404, detail="Staff not Found")

    existing_staff = membership.staff_member

    update_data = staff.model_dump(exclude_unset=True)
    if "password" in update_data:
        update_data["hashed_password"] = update_data.pop("password") 

    for field, value in update_data.items():
        setattr(existing_staff, field, value)

    await db.commit()
    await db.refresh(existing_staff)
    return existing_staff


@router.delete("/router/staff/{college_id}/{staff_id}", status_code=204)
async def delete_staff(staff_id: int, college_id: int, db: AsyncSession = Depends(get_db)):
    college_exists = await db.execute(select(College.college_id).where(College.college_id == college_id).limit(1))
    if not college_exists.scalar():
        raise HTTPException(status_code=404, detail="College not found")
    existing_staff_result = await db.execute(select(StaffCollege).where(StaffCollege.college_id == college_id, StaffCollege.staff_id == staff_id).options(selectinload(StaffCollege.staff_member)).limit(1))
    existing_staff = existing_staff_result.scalars().first()
    if not existing_staff:
        raise HTTPException(status_code=404, detail="Staff not Found")

    await db.delete(existing_staff.staff_member)
    await db.commit()