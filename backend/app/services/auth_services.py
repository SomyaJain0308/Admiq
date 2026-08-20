from datetime import datetime, UTC, timedelta
import jwt
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash

from backend.app.config import get_settings


settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/token")

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hasher.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key.get_secret_value(), algorithm=settings.algorithm)
    return encoded_jwt


def verify_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.secret_key.get_secret_value(), algorithms=[settings.algorithm], options={"require": ["exp", "sub"]})
    except jwt.InvalidTokenError:
        return None
    else:
        return payload.get("sub")
