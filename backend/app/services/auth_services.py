from datetime import datetime, UTC, timedelta
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models.CollegeStaff_StaffCollege import CollegeStaff, StaffCollege
from backend.app.config import get_settings


settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/token")

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hasher.verify(plain_password, hashed_password)


def _create_token(data: dict, expires_data: timedelta, token_type: str) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + expires_data
    to_encode.update({"exp": expire, "type": token_type})
    return jwt.encode(to_encode, settings.secret_key.get_secret_value(), algorithm=settings.algorithm)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    expires_delta = expires_delta or timedelta(settings.access_token_expire_days)
    return _create_token(data, expires_delta, token_type="access")


def create_refresh_token(data: dict, expires_delta: timedelta | None = None):
    expires_delta = expires_delta or timedelta(days=settings.refresh_token_expire_days)
    return _create_token(data, expires_delta, token_type="refresh")


def _verify_token(token: str, expected_type: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.secret_key.get_secret_value(), algorithms=[settings.algorithm], options={"require": ["exp", "sub"]})
    except jwt.InvalidTokenError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload.get("sub")


def verify_access_token(token: str) -> str | None:
    return _verify_token(token, expected_type="access")


def verify_refresh_token(token: str) -> str | None:
    return _verify_token(token, expected_type="refresh")


async def get_current_staff(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> CollegeStaff:
    staff_id = verify_access_token(token)
    if staff_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    try:
        staff_id_int = int(staff_id)  # Defense against malformed jwt
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    staff_result = await db.execute(select(CollegeStaff).where(CollegeStaff.staff_id == staff_id_int).limit(1))
    staff = staff_result.scalars().first()
    if not staff:
        raise HTTPException(status_code=401, detail="Staff not found", headers={"WWW-Authenticate": "Bearer"})
    return staff


async def verify_college_access(college_id: int, db: AsyncSession = Depends(get_db), current_staff: CollegeStaff = Depends(get_current_staff)) -> StaffCollege:
    membership_result = await db.execute(select(StaffCollege).where(StaffCollege.college_id == college_id, StaffCollege.staff_id == current_staff.staff_id).limit(1))
    membership = membership_result.scalars().first()
    if not membership:
        raise HTTPException(status_code=403, detail="You do not have access to this college")
    return membership