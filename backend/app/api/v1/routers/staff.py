import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_limiter.depends import RateLimiter
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.database import get_db
from backend.app.models.CollegeStaff_StaffCollege import CollegeStaff, StaffCollege
from backend.app.models.College import College
from backend.app.schemas.staff import RefreshTokenRequest, StaffCreate, StaffResponse, StaffUpdate, Token, CurrentStaffResponse, ForgotPasswordRequest, ResetPasswordRequest
from backend.app.services.auth_services import create_access_token, revoke_refresh_token, verify_college_access, get_current_staff, verify_password, hash_password, create_refresh_token, verify_refresh_token, create_password_reset_token, verify_password_reset_token, revoke_password_reset_token, create_staff_invite_token
from backend.app.services.email_service import send_password_reset_email, send_staff_invite_email
from backend.app.services.csv_export import rows_to_csv_response
from backend.app.config import get_settings



settings = get_settings()

router = APIRouter(tags=["staff"])



@router.get("/me", response_model=CurrentStaffResponse)
async def read_current_staff(current_staff: CollegeStaff = Depends(get_current_staff), db: AsyncSession = Depends(get_db)):
    colleges_result = await db.execute(select(College).join(StaffCollege, StaffCollege.college_id == College.college_id).where(StaffCollege.staff_id == current_staff.staff_id))
    colleges = colleges_result.scalars().all()
    return CurrentStaffResponse(staff_id=current_staff.staff_id, staff_name=current_staff.staff_name, staff_email=current_staff.staff_email, is_active=current_staff.is_active, created_at=current_staff.created_at, colleges=colleges)
    

@router.get("/router/staff/{college_id}")
async def get_staff(
    college_id: int,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_staff: CollegeStaff = Depends(verify_college_access),
):
    college_exists = await db.execute(select(College.college_id).where(College.college_id == college_id).limit(1))
    if not college_exists.scalar():
        raise HTTPException(status_code=404, detail="College not found")

    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    base_query = select(StaffCollege).where(StaffCollege.college_id == college_id).options(selectinload(StaffCollege.staff_member))
    count_query = select(func.count()).select_from(StaffCollege).join(CollegeStaff, CollegeStaff.staff_id == StaffCollege.staff_id).where(StaffCollege.college_id == college_id)

    if search:
        term = f"%{search.strip()}%"
        search_filter = or_(CollegeStaff.staff_name.ilike(term), CollegeStaff.staff_email.ilike(term))
        base_query = base_query.join(CollegeStaff, CollegeStaff.staff_id == StaffCollege.staff_id).where(search_filter)
        count_query = count_query.where(search_filter)

    total = (await db.execute(count_query)).scalar_one()

    base_query = base_query.order_by(CollegeStaff.staff_name.asc()).offset((page - 1) * page_size).limit(page_size)
    staff_results = await db.execute(base_query)
    staff = staff_results.scalars().all()
    return {"items": [s.staff_member for s in staff], "total": total, "page": page, "page_size": page_size}


@router.get("/router/staff/{college_id}/export")
async def export_staff(
    college_id: int,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_staff: CollegeStaff = Depends(verify_college_access),
):
    query = select(StaffCollege).where(StaffCollege.college_id == college_id).options(selectinload(StaffCollege.staff_member))
    if search:
        term = f"%{search.strip()}%"
        query = query.join(CollegeStaff, CollegeStaff.staff_id == StaffCollege.staff_id).where(or_(CollegeStaff.staff_name.ilike(term), CollegeStaff.staff_email.ilike(term)))
    query = query.order_by(CollegeStaff.staff_name.asc())
    staff_results = await db.execute(query)
    staff = [s.staff_member for s in staff_results.scalars().all()]

    rows = [
        {
            "staff_name": s.staff_name,
            "staff_email": s.staff_email,
            "is_active": s.is_active,
            "created_at": s.created_at.isoformat() if s.created_at else "",
        }
        for s in staff
    ]
    columns = ["staff_name", "staff_email", "is_active", "created_at"]
    return rows_to_csv_response(rows, columns, filename=f"staff_college_{college_id}.csv")


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
async def create_staff(college_id: int, staff: StaffCreate, db: AsyncSession = Depends(get_db), current_staff: CollegeStaff = Depends(get_current_staff)):
    college_result = await db.execute(select(College.college_id, College.college_name).where(College.college_id == college_id).limit(1))
    college_row = college_result.first()
    if not college_row:
        raise HTTPException(status_code=404, detail="College not found")
    college_name = college_row.college_name

    college_has_staff = await db.execute(select(StaffCollege.staff_id).where(StaffCollege.college_id == college_id).limit(1))
    if college_has_staff.scalar() is not None:
        caller_membership = await db.execute(select(StaffCollege).where(StaffCollege.college_id == college_id, StaffCollege.staff_id == current_staff.staff_id).limit(1))
        if not caller_membership.scalars().first():
            raise HTTPException(status_code=403, detail="You do not have access to this college")

    existing_staff_result = await db.execute(select(CollegeStaff).where(func.lower(CollegeStaff.staff_email) == staff.staff_email.lower()).limit(1))
    existing_staff = existing_staff_result.scalars().first()

    if existing_staff:  # We can't do both the db calls in one it's intentional.
        membership_result = await db.execute(select(StaffCollege).where(StaffCollege.college_id == college_id, StaffCollege.staff_id == existing_staff.staff_id).limit(1))
        if membership_result.scalars().first():
            raise HTTPException(status_code=409, detail=f"'{staff.staff_email}' is already staff at this college")

        membership = StaffCollege(staff_id=existing_staff.staff_id, college_id=college_id)
        db.add(membership)
        await db.commit()
        await db.refresh(existing_staff)
        return existing_staff

    # No password given -> invite flow: create the account with a random,
    # never-revealed password (nobody can log in with it, including us) and
    # email them a link to set their own. If a password was given instead,
    # skip all of this and use it directly - some admins prefer handing
    # someone credentials in person over email.
    invite_sent = staff.password is None
    actual_password = staff.password or secrets.token_urlsafe(32)

    new_staff = CollegeStaff(staff_name=staff.staff_name, staff_email=staff.staff_email.lower(), is_active=staff.is_active, hashed_password=hash_password(actual_password))
    db.add(new_staff)
    await db.flush()

    membership = StaffCollege(staff_id=new_staff.staff_id, college_id=college_id)
    db.add(membership)
    await db.commit()
    await db.refresh(new_staff)

    if invite_sent:
        invite_token = create_staff_invite_token(new_staff.staff_id)
        invite_link = f"{settings.frontend_url}/reset-password?token={invite_token}"
        await send_staff_invite_email(new_staff.staff_email, new_staff.staff_name, college_name, invite_link)

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


@router.post("/logout", status_code=204)
async def logout(payload: RefreshTokenRequest):
    await revoke_refresh_token(payload.refresh_token)


@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    staff_result = await db.execute(select(CollegeStaff).where(func.lower(CollegeStaff.staff_email) == form_data.username.lower()).limit(1))
    staff = staff_result.scalars().first()
    if not staff or not verify_password(form_data.password, staff.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"}) # password or email is incorrect is the norm, otherwise it would be very easy for hackers to attack
    access_token = create_access_token(data={"sub": str(staff.staff_id)})
    refresh_token = create_refresh_token(data={"sub": str(staff.staff_id)})
    return Token(access_token=access_token, refresh_token=refresh_token, token_type="Bearer")


@router.post("/refresh", response_model=Token)
async def refresh_access_token(payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    staff_id = await verify_refresh_token(payload.refresh_token)
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
    await revoke_refresh_token(payload.refresh_token) # Expire the old token as soon as a new one is issued
    return Token(access_token=new_access_token, refresh_token=new_refresh_token, token_type="Bearer")


@router.post("/forgot-password", status_code=204, dependencies=[Depends(RateLimiter(times=3, minutes=15))])
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    # Always returns 204 whether or not the email exists - responding
    # differently would let anyone probe which staff emails are registered
    # (account enumeration). The rate limit above is the real defense against
    # someone hammering this to spam an inbox with reset links.
    staff_result = await db.execute(select(CollegeStaff).where(func.lower(CollegeStaff.staff_email) == payload.staff_email.lower()).limit(1))
    staff = staff_result.scalars().first()
    if staff:
        reset_token = create_password_reset_token(staff.staff_id)
        reset_link = f"{settings.frontend_url}/reset-password?token={reset_token}"
        await send_password_reset_email(staff.staff_email, reset_link)


@router.post("/reset-password", status_code=204)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    staff_id = await verify_password_reset_token(payload.token)
    if staff_id is None:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired. Please request a new one.")
    staff_result = await db.execute(select(CollegeStaff).where(CollegeStaff.staff_id == int(staff_id)).limit(1))
    staff = staff_result.scalars().first()
    if not staff:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired. Please request a new one.")
    staff.hashed_password = hash_password(payload.new_password)
    await db.commit()
    await revoke_password_reset_token(payload.token)  # single-use - can't be replayed