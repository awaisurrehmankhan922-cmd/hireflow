"""Admin authentication (bcrypt + JWT) and webhook HMAC verification."""
import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import AdminUser

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)
COOKIE = "hf_token"


def hash_password(p: str) -> str:
    return pwd.hash(p)


def verify_password(p: str, h: str) -> bool:
    return pwd.verify(p, h)


def create_token(email: str) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.jwt_expire_minutes)
    return jwt.encode({"sub": email, "exp": exp}, s.jwt_secret, algorithm="HS256")


def current_admin(request: Request, token: str | None = Depends(oauth2), db: Session = Depends(get_db)) -> AdminUser:
    token = token or request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        email = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])["sub"]
    except (JWTError, KeyError):
        raise HTTPException(401, "Invalid token")
    user = db.query(AdminUser).filter_by(email=email, is_active=True).first()
    if not user:
        raise HTTPException(401, "Inactive user")
    return user


async def verify_webhook(request: Request, x_hireflow_signature: str = Header(""),
                         x_hireflow_timestamp: str = Header("")) -> bytes:
    """HMAC-SHA256(secret, f"{timestamp}.{body}") with 5-minute replay window."""
    body = await request.body()
    try:
        ts = int(x_hireflow_timestamp)
    except ValueError:
        raise HTTPException(401, "Missing timestamp")
    if abs(time.time() - ts) > 300:
        raise HTTPException(401, "Stale request")
    expected = hmac.new(get_settings().webhook_secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_hireflow_signature):
        raise HTTPException(401, "Bad signature")
    return body
