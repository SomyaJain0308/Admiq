from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_limiter.depends import RateLimiter
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.database import get_db
from backend.app.models.CollegeStaff_StaffCollege import CollegeStaff, StaffCollege
from backend.app.models.College import College
from backend.app.schemas.staff import RefreshTokenRequest, StaffCreate, StaffResponse, StaffUpdate, Token
from backend.app.services.auth_services import create_access_token, verify_college_access, get_current_staff, verify_password, hash_password, create_refresh_token, verify_refresh_token
from backend.app.config import get_settings



settings = get_settings()

router = APIRouter(tags=["staff"])



@router.get("/me", response_model=StaffResponse)
async def read_current_staff(current_staff: CollegeStaff = Depends(get_current_staff)):
    return current_staff
    

@router.get("/router/staff/{college_id}", response_model=list[StaffResponse])
async def get_staff(college_id: int, db: AsyncSession = Depends(get_db), current_staff: CollegeStaff = Depends(verify_college_access)):
    college_exists = await db.execute(select(College.college_id).where(College.college_id == college_id).limit(1))
    if not college_exists.scalar():
        raise HTTPException(status_code=404, detail="College not found")
    staff_results = await db.execute(select(StaffCollege).where(StaffCollege.college_id == college_id).options(selectinload(StaffCollege.staff_member)))
    staff = staff_results.scalars().all()
    if not staff:
        raise HTTPException(status_code=404, detail="No staff exist yet for this college")
    return [s.staff_member for s in staff]


@router.get("/router/staff/{college_id}/{staff_id}", response_model=StaffResponse)
async def get_staff_by_id(staff_id: int, college_id: int, db: AsyncSession = Depends(get_db), current_staff: CollegeStaff = Depends(verify_college_access)):
    college_exists = await db.execute(select(College.college_id).where(College.college_id == college_id).limit(1))
    if not college_exists.scalar():
        raise HTTPException(status_code=404, detail="College not found")
    existing_staff_result = await db.execute(select(StaffCollege).where(StaffCollege.college_id == college_id, StaffCollege.staff_id == staff_id).options(selectinload(StaffCollege.staff_member)).limit(1))
    existing_staff = existing_staff_result.scalars().first()
    if not existing_staff:
        raise HTTPException(status_code=404, detail="Staff not Found")
    return existing_staff.staff_member


@router.post("/router/staff/{college_id}", response_model=StaffResponse, status_code=201)
async def create_staff(college_id: int, staff: StaffCreate, db: AsyncSession = Depends(get_db), current_staff: CollegeStaff = Depends(verify_college_access)):
    college_exists = await db.execute(select(College.college_id).where(College.college_id == college_id).limit(1))
    if not college_exists.scalar():
        raise HTTPException(status_code=404, detail="College not found")

    existing_staff_result = await db.execute(select(CollegeStaff).where(func.lower(CollegeStaff.staff_email) == staff.staff_email.lower()).limit(1))
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

    new_staff = CollegeStaff(staff_name=staff.staff_name, staff_email=staff.staff_email.lower(), is_active=staff.is_active, hashed_password=hash_password(staff.password))
    db.add(new_staff)
    await db.flush()

    membership = StaffCollege(staff_id=new_staff.staff_id, college_id=college_id)
    db.add(membership)
    await db.commit()
    await db.refresh(new_staff)
    return new_staff


@router.patch("/router/staff/{college_id}/{staff_id}", response_model=StaffResponse)
async def update_staff(staff_id: int, college_id: int, staff: StaffUpdate, db: AsyncSession = Depends(get_db), current_staff: CollegeStaff = Depends(verify_college_access)):
    college_exists = await db.execute(select(College.college_id).where(College.college_id == college_id).limit(1))
    if not college_exists.scalar():
        raise HTTPException(status_code=404, detail="College not found")

    existing_staff_result = await db.execute(select(StaffCollege).where(StaffCollege.college_id == college_id, StaffCollege.staff_id == staff_id).options(selectinload(StaffCollege.staff_member)).limit(1))
    membership = existing_staff_result.scalars().first()
    if not membership:
        raise HTTPException(status_code=404, detail="Staff not Found")

    existing_staff = membership.staff_member

    update_data = staff.model_dump(exclude_unset=True)
    if "password" in update_data:
        update_data["hashed_password"] = hash_password(update_data.pop("password"))
    if "staff_email" in update_data:
        update_data["staff_email"] = update_data["staff_email"].lower()
    for field, value in update_data.items():
        setattr(existing_staff, field, value)

    await db.commit()
    await db.refresh(existing_staff)
    return existing_staff


@router.delete("/router/staff/{college_id}/{staff_id}", status_code=204)
async def delete_staff(staff_id: int, college_id: int, db: AsyncSession = Depends(get_db), current_staff: CollegeStaff = Depends(verify_college_access)):
    college_exists = await db.execute(select(College.college_id).where(College.college_id == college_id).limit(1))
    if not college_exists.scalar():
        raise HTTPException(status_code=404, detail="College not found")
    existing_staff_result = await db.execute(select(StaffCollege).where(StaffCollege.college_id == college_id, StaffCollege.staff_id == staff_id).options(selectinload(StaffCollege.staff_member)).limit(1))
    existing_staff = existing_staff_result.scalars().first()
    if not existing_staff:
        raise HTTPException(status_code=404, detail="Staff not Found")

    await db.delete(existing_staff.staff_member)
    await db.commit()


@router.post("/token", response_model=Token, dependencies=[Depends(RateLimiter(times=5, seconds=60))])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    staff_result = await db.execute(select(CollegeStaff).where(func.lower(CollegeStaff.staff_email) == form_data.username.lower()).limit(1))
    staff = staff_result.scalars().first()
    if not staff or not verify_password(form_data.password, staff.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"}) # password or email is incorrect is the norm, otherwise it would be very easy for hackers to attack
    access_token = create_access_token(data={"sub": str(staff.staff_id)})
    refresh_token = create_refresh_token(data={"sub": str(staff.staff_id)})
    return Token(access_token=access_token, refresh_token=refresh_token, token_type="bearer")


@router.post("/refresh", response_model=Token, dependencies=[Depends(RateLimiter(times=5, seconds=60))])
async def refresh_access_token(payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    staff_id = verify_refresh_token(payload.refresh_token)
    if staff_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token", headers={"WWW-Authenticate": "Bearer"})
    try:
        staff_id_int = int(staff_id) # Protection against malformed staff_id
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token", headers={"WWW-Authenticate": "Bearer"})
    staff_result = await db.execute(select(CollegeStaff).where(CollegeStaff.staff_id == staff_id_int).limit(1))
    staff = staff_result.scalars().first()
    if not staff:
        raise HTTPException(status_code=401, detail="Staff not found", headers={"WWW-Authenticate": "Bearer"})
    new_access_token = create_access_token(data={"sub": str(staff.staff_id)})
    new_refresh_token = create_refresh_token(data={"sub": str(staff.staff_id)})
    return Token(access_token=new_access_token, refresh_token=new_refresh_token, token_type="Bearer")