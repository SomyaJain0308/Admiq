import jwt
import redis.asyncio as redis
from uuid import uuid4
from datetime import datetime, UTC, timedelta
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models.CollegeStaff_StaffCollege import CollegeStaff, StaffCollege
from backend.app.config import get_settings


settings = get_settings()

# Extract the JWT out of the Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token") # Creates a reusable dependency ( FastAPI Uses dependencies like: "something: Type = Depends(some_function)" so for e.g. "db: Session = Depends(get_db)" before the route code runs fastapi calls some_function() or get_db() for me) 

password_hasher = PasswordHash.recommended() # Actually hashes the password

_redis_client: redis.Redis | None = None

def get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    return _redis_client

def hash_password(password: str) -> str:
    return password_hasher.hash(password) # PlainPassword -> HashedPassword


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return password_hasher.verify(plain_password, hashed_password)
    except Exception:
        return False # While login u can't unhash the pass and then check it so you hash the provided pass the same way and see if the hashed password (which was stored in db) and the password provided by user during login matches


def _create_token(data: dict, expires_data: timedelta, token_type: str) -> str: # Data -> {"sub": "x"} meaning "subject = staff ID x"
    to_encode = data.copy() # Fancy way of doing nothing
    expire = datetime.now(UTC) + expires_data
    to_encode.update({"exp": expire, "type": token_type, "jti": str(uuid4())})
    return jwt.encode(to_encode, settings.secret_key.get_secret_value(), algorithm=settings.algorithm)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    expires_delta = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    return _create_token(data, expires_delta, token_type="access")


def create_refresh_token(data: dict, expires_delta: timedelta | None = None):
    expires_delta = expires_delta or timedelta(days=settings.refresh_token_expire_days)
    return _create_token(data, expires_delta, token_type="refresh")


def _decode_token(token: str, expected_type: str) -> str | None: # Given a token string decode the signature (the secret_key in .env which is server side)
    try:
        payload = jwt.decode(token, settings.secret_key.get_secret_value(), algorithms=[settings.algorithm], options={"require": ["exp", "sub", "jti"]})
    except jwt.InvalidTokenError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload


def verify_access_token(token: str) -> str | None:
    payload = _decode_token(token, expected_type="access")
    return payload.get("sub") if payload else None


async def is_token_revoked(jti: str) -> bool:
    redis_client = get_redis_client()
    return bool(await redis_client.exists(f"revoked_jti:{jti}")) # The statement inside bool returns 0 (False) or 1 (True) which is converted int tru or false by the bool func. The func inside bool checks redis for a key named "revoked_jti:<the token's jti>"


async def verify_refresh_token(token: str) -> str | None:
    payload = _decode_token(token, expected_type="refresh")
    if payload is None:
        return None
    jti = payload.get("jti")
    if jti and await is_token_revoked(jti):
        return None
    return payload.get("sub")


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
    if not staff: # confirm the staff member still actually exists (they might have been deleted after the token was issued)
        raise HTTPException(status_code=401, detail="Staff not found", headers={"WWW-Authenticate": "Bearer"})
    return staff


async def verify_college_access(college_id: int, db: AsyncSession = Depends(get_db), current_staff: CollegeStaff = Depends(get_current_staff)) -> StaffCollege:
    membership_result = await db.execute(select(StaffCollege).where(StaffCollege.college_id == college_id, StaffCollege.staff_id == current_staff.staff_id).limit(1))
    membership = membership_result.scalars().first()
    if not membership:
        raise HTTPException(status_code=403, detail="You do not have access to this college")
    return membership


async def revoke_refresh_token(token: str) -> None: # Marks a refresh token's jti as revoked in Redis until it expires (7 days in this case). logout should not fail just because the token was alr dead or expired
    payload = _decode_token(token, expected_type="refresh")
    if payload is None:
        return
    jti = payload.get("jti")
    exp_ts = payload.get("exp")
    if not jti or not exp_ts:
        return
    ttl_seconds = int(exp_ts - datetime.now(UTC).timestamp())
    if ttl_seconds <= 0:
        return
    redis_client = get_redis_client()
    await redis_client.set(f"revoked_jti:{jti}", "1", ex=ttl_seconds) # Mark the key in redis revoked and set an expiry date