import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models.College import College
from backend.app.models.CollegeStaff_StaffCollege import CollegeStaff
from backend.app.models.WhatsappNumber import WhatsAppNumber
from backend.app.services.auth_services import verify_college_access
from backend.app.schemas.colleges import CollegeCreate, CollegeUpdate, CollegeResponse
from backend.app.schemas.whatsapp_number import WhatsAppNumberCreate, WhatsAppNumberResponse
from backend.app.config import get_settings


router = APIRouter(tags=["colleges"])


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

    # Server-generated, never client-supplied: 24 bytes of urlsafe randomness
    # (192 bits) makes a collision astronomically unlikely, so a single
    # generation is fine - no retry loop needed the way the name/email/phone
    # checks above are.
    widget_public_key = "admiq_pub_" + secrets.token_urlsafe(24)

    new_college = College(
        college_name=college.college_name,
        college_phone=college.college_phone,
        college_email=college.college_email,
        college_strengths=college.college_strengths,
        widget_public_key=widget_public_key,
        widget_allowed_origin=college.widget_allowed_origin,
    )
    
    db.add(new_college)
    await db.commit()
    await db.refresh(new_college)
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
