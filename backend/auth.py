"""Authentication & Role-Based Access Control (RBAC) utilities.

Uses bcrypt for password hashing and PyJWT (HS256) for stateless bearer tokens.
Supports three stakeholder roles: 'traveler', 'analyst', and 'admin'.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from database.db import get_user_by_id

SECRET_KEY = os.getenv("FARELENS_JWT_SECRET") or os.getenv("AEROPRICE_JWT_SECRET") or os.getenv("JWT_SECRET") or "farelens-g1716-dev-secret-2026"
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    salt = bcrypt.gensalt(rounds=10)
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(user_id: int, email: str, role: str, full_name: str) -> str:
    """Create a signed JWT token containing user identity and role claims."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "name": full_name,
        "jti": secrets.token_hex(8),
        "iat": now,
        "exp": now + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT bearer token."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please sign in again.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[dict]:
    """Return the authenticated user dict if a valid Bearer token is present, else None."""
    if credentials is None or not credentials.credentials:
        return None
    claims = decode_access_token(credentials.credentials)
    user = get_user_by_id(int(claims["sub"]))
    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account inactive or not found.",
        )
    return user


def get_current_user(
    user: Optional[dict] = Depends(get_optional_user),
) -> dict:
    """Require an authenticated active user; raise 401 otherwise."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Sign in or register to continue.",
        )
    return user


def require_roles(*allowed_roles: str) -> Callable:
    """Dependency factory enforcing RBAC role authorization."""

    def _role_guard(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {', '.join(allowed_roles)}.",
            )
        return user

    return _role_guard
