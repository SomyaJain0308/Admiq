import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models.College import College
from backend.app.models.CollegeStaff_StaffCollege import CollegeStaff, StaffCollege
from backend.app.models.WhatsappNumber import WhatsAppNumber
from backend.app.services.auth_services import verify_college_access, hash_password, create_staff_invite_token
from backend.app.services.email_service import send_staff_invite_email
from backend.app.schemas.colleges import CollegeCreate, CollegeUpdate, CollegeResponse
from backend.app.schemas.whatsapp_number import WhatsAppNumberCreate, WhatsAppNumberResponse
from backend.app.config import get_settings


router = APIRouter(tags=["colleges"])
settings = get_settings()


# create_college, delete_college, and get_colleges (list-all) are ops-only
# actions with no natural staff-level authorization: creating a brand-new
# college happens before any staff exists for it, deleting one is a
# destructive superadmin action, and listing every college in the system
# would leak every tenant's name/contact info to any single staff member if
# left open to verify_college_access. None of these are called by the
# dashboard frontend - they're for manual/ops use (e.g. via curl or
# Postman) - so they're gated the same way the internal scheduled-task
# endpoints are: a shared secret in a header, fails closed if unconfigured.
def _verify_admin_token(x_admin_token: str | None) -> None:
    settings = get_settings()
    if not settings.internal_task_token:
        raise HTTPException(status_code=503, detail="internal_task_token not configured")
    if x_admin_token != settings.internal_task_token:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Token")


@router.get("/router/college", response_model=list[CollegeResponse])
async def get_colleges(db: AsyncSession = Depends(get_db), x_admin_token: str | None = Header(default=None)):
    _verify_admin_token(x_admin_token)
    colleges_result = await db.execute(select(College))
    colleges = colleges_result.scalars().all()
    if colleges:  
        return colleges
    else:
        raise HTTPException(status_code=404, detail="No colleges exist yet")


@router.get("/router/college/{college_id}", response_model=CollegeResponse)
async def get_college(college_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    existing_college_result = await db.execute(select(College).where(College.college_id == college_id).limit(1))
    existing_college = existing_college_result.scalars().first()
    if existing_college:
        return existing_college
    else:
        raise HTTPException(status_code=404, detail="College not Found")


@router.post("/router/colleges", response_model=CollegeResponse, status_code=201)
async def create_college(college: CollegeCreate, db: AsyncSession = Depends(get_db), x_admin_token: str | None = Header(default=None)):
    _verify_admin_token(x_admin_token)
    existing_college_result = await db.execute(select(College).where(College.college_name == college.college_name).limit(1))
    existing_college = existing_college_result.scalars().first()
    if existing_college:
        raise HTTPException(status_code=409, detail=f"College '{college.college_name}' already exists")
    
    existing_email_result = await db.execute(select(College).where(College.college_email == college.college_email).limit(1))
    existing_email = existing_email_result.scalars().first()
    if existing_email:
        raise HTTPException(status_code=409, detail=f"Email '{college.college_email}' already exists")

    existing_phone_number_result = await db.execute(select(College).where(College.college_phone == college.college_phone).limit(1))
    existing_phone_number = existing_phone_number_result.scalars().first()
    if existing_phone_number:
        raise HTTPException(status_code=409, detail=f"Phone Number '{college.college_phone}' already exists")

    new_college = College(
        college_name=college.college_name,
        college_phone=college.college_phone,
        college_email=college.college_email,
        college_strengths=college.college_strengths
    )
    db.add(new_college)
    await db.flush()  # assigns new_college.college_id without committing yet - staff creation below can still fail and roll both back

    # Bootstrap the first staff member in the same transaction: a brand-new
    # college has no staff, and create_staff's own bootstrap path (any
    # logged-in staff can create the first staff row for an empty college)
    # still requires *some* staff account to already be logged in. Doing it
    # here instead removes that dependency entirely for the first college.
    staff_in = college.first_staff
    existing_staff_result = await db.execute(select(CollegeStaff).where(func.lower(CollegeStaff.staff_email) == staff_in.staff_email.lower()).limit(1))
    existing_staff = existing_staff_result.scalars().first()

    if existing_staff:
        # Same email already has an account elsewhere - attach them to this
        # college instead of creating a second account, mirroring create_staff.
        new_staff = existing_staff
        invite_sent = False
    else:
        invite_sent = staff_in.password is None
        actual_password = staff_in.password or secrets.token_urlsafe(32)
        new_staff = CollegeStaff(
            staff_name=staff_in.staff_name,
            staff_email=staff_in.staff_email.lower(),
            is_active=staff_in.is_active,
            hashed_password=hash_password(actual_password),
        )
        db.add(new_staff)
        await db.flush()  # assigns new_staff.staff_id

    membership = StaffCollege(staff_id=new_staff.staff_id, college_id=new_college.college_id)
    db.add(membership)

    await db.commit()
    await db.refresh(new_college)

    if invite_sent:
        invite_token = create_staff_invite_token(new_staff.staff_id)
        invite_link = f"{settings.frontend_url}/home/reset-password?token={invite_token}"
        await send_staff_invite_email(new_staff.staff_email, new_staff.staff_name, new_college.college_name, invite_link)

    return new_college


@router.patch("/router/college/{college_id}", response_model=CollegeResponse)
async def update_college(college_id: int, college: CollegeUpdate, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    existing_college_result = await db.execute(select(College).where(College.college_id == college_id).limit(1))
    existing_college = existing_college_result.scalars().first()
    if not existing_college:
        raise HTTPException(status_code=404, detail="College not Found")

    college = college.model_dump(exclude_unset=True)
    for field, value in college.items():
        setattr(existing_college, field, value)

    await db.commit()
    await db.refresh(existing_college)
    return existing_college


@router.delete("/router/college/{college_id}", status_code=204)
async def delete_college(college_id: int, db: AsyncSession = Depends(get_db), x_admin_token: str | None = Header(default=None)):
    _verify_admin_token(x_admin_token)
    existing_college_result = await db.execute(select(College).where(College.college_id == college_id).limit(1))
    existing_college = existing_college_result.scalars().first()
    if not existing_college:
        raise HTTPException(status_code=404, detail="College not Found")
    await db.delete(existing_college)
    await db.commit()


# Registering a college's WhatsApp Business number is ops-only for the same
# reason create_college is: there's no natural staff-level authorization for
# it, and the values involved (Meta's phone_number_id and WhatsApp Business
# Account ID) come from a college's Meta Business Manager setup that AdmiQ's
# own team coordinates during onboarding, not something college staff supply
# through their dashboard. Without a row here, the webhook has no way to
# match an inbound message's phone_number_id to a college at all - this was
# previously only reachable by inserting directly into the database.
@router.post("/router/college/{college_id}/whatsapp-number", response_model=WhatsAppNumberResponse, status_code=201)
async def create_whatsapp_number(college_id: int, payload: WhatsAppNumberCreate, db: AsyncSession = Depends(get_db), x_admin_token: str | None = Header(default=None)):
    _verify_admin_token(x_admin_token)

    existing_college_result = await db.execute(select(College).where(College.college_id == college_id).limit(1))
    existing_college = existing_college_result.scalars().first()
    if not existing_college:
        raise HTTPException(status_code=404, detail="College not Found")

    existing_number_result = await db.execute(select(WhatsAppNumber).where(WhatsAppNumber.phone_number_id == payload.phone_number_id).limit(1))
    existing_number = existing_number_result.scalars().first()
    if existing_number:
        raise HTTPException(status_code=409, detail=f"phone_number_id '{payload.phone_number_id}' is already registered (college_id={existing_number.college_id})")

    new_number = WhatsAppNumber(
        college_id=college_id,
        phone_number_id=payload.phone_number_id,
        whatsapp_business_account_id=payload.whatsapp_business_account_id,
        display_number=payload.display_number,
    )
    db.add(new_number)
    await db.commit()
    await db.refresh(new_number)
    return new_number


@router.get("/router/college/{college_id}/whatsapp-number", response_model=WhatsAppNumberResponse)
async def get_whatsapp_number(college_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    # Staff-level (not admin-gated) - unlike registering one, checking
    # whether your own college's WhatsApp number is connected is a
    # reasonable thing for that college's own staff to see.
    number_result = await db.execute(select(WhatsAppNumber).where(WhatsAppNumber.college_id == college_id).limit(1))
    number = number_result.scalars().first()
    if not number:
        raise HTTPException(status_code=404, detail="No WhatsApp number is connected for this college yet")
    return number
