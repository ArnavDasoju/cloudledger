"""Authentication — JWT-based register/login with per-user data isolation."""

import logging
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException, Request
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

JWT_SECRET = os.getenv("JWT_SECRET", "cloudledger-dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 72
_MIN_SECRET_BYTES = 32

if len(JWT_SECRET.encode("utf-8")) < _MIN_SECRET_BYTES:
    logger.warning(
        "JWT_SECRET is %d bytes, below the %d-byte minimum for HS256. "
        "Set a stronger secret via the JWT_SECRET environment variable.",
        len(JWT_SECRET.encode("utf-8")),
        _MIN_SECRET_BYTES,
    )


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_token(user_id: int, email: str) -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(401, f"Invalid token: {e}")


def get_current_user_id(request: Request) -> int:
    """Extract user_id from the Authorization: Bearer <token> header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")
    token = auth[7:]
    payload = decode_token(token)
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(401, "Invalid token payload")
    return int(user_id)
