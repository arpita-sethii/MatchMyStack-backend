# backend/app/core/security.py
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import Dict, Any

from app.core.config import JWT_SECRET, ACCESS_TOKEN_EXPIRE_MINUTES

# Use Argon2 as primary scheme (no 72-byte limit); keep bcrypt allowed as fallback if desired
pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict, expires_minutes: int = None) -> str:
    """
    Create a JWT access token.
    The exp claim is stored as an integer unix timestamp.
    """
    expire_dt = datetime.utcnow() + timedelta(minutes=(expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES))
    # use numeric timestamp for exp
    to_encode = data.copy()
    to_encode.update({"exp": int(expire_dt.replace(tzinfo=timezone.utc).timestamp())})
    token = jwt.encode(to_encode, JWT_SECRET, algorithm="HS256")
    return token

def verify_token(token: str) -> Dict[str, Any]:
    """
    Decode and verify a JWT token. Raises HTTPException on failure.
    Returns the token payload (claims) on success.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # At minimum ensure there's a subject
    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: subject (sub) missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload