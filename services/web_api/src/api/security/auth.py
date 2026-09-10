import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from src.api.db.models import User, UserRole
from src.api.db.session import get_db

JWT_SECRET = os.getenv("JWT_SECRET", "ukvi-credibility-jwt-secret-key-must-be-32-chars-long-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 10


def hash_password(password: str) -> str:
    """Hashes a password using PBKDF2 HMAC-SHA256 with a secure random salt."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against the stored salt$hash."""
    try:
        salt, key_hex = hashed_password.split("$", 1)
        expected_key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), 100_000)
        return hmac.compare_digest(expected_key.hex(), key_hex)
    except Exception:
        return False


def create_access_token(user_id: str, role: str, device_id: str) -> str:
    """
    Issues a cryptographically signed JWT with a 10-day expiration window
    and binding to a client device identifier for single-device lockdown.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "role": role,
        "device_id": device_id,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decodes and verifies token signature and expiration."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired. Please log in again.",
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )


def get_current_user(
    access_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency extracting JWT from HTTP-only cookie or Authorization header.
    Enforces the Single-Device Lockdown Invariant:
    If token.device_id != user.active_device_id, access is immediately denied.
    """
    token = access_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
        )

    payload = decode_access_token(token)
    user_id = payload.get("sub")
    token_device_id = payload.get("device_id")

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or deactivated.",
        )

    # Enforce Single-Device Lockdown Invariant
    if user.active_device_id and user.active_device_id != token_device_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session terminated. Your account has been logged in from another device.",
        )

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Ensures the authenticated user possesses the ADMIN role."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required.",
        )
    return current_user
