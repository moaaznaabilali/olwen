"""Authentication routes: register, verify email, login, refresh."""
import datetime as dt
import logging
import time
import uuid
from collections import defaultdict
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.core.config import settings  # noqa: F401
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_otp,
    hash_otp,
    hash_password,
    verify_otp,
    verify_password,
)
from app.models.email_otp import EmailOTP
from app.models.user import User
from app.schemas.user import (
    RefreshRequest,
    RegisterResponse,
    ResendRequest,
    Token,
    UserCreate,
    VerifyEmailRequest,
)
from app.services.email import send_otp_email

router = APIRouter()
logger = logging.getLogger("olwen.auth")

# In-memory login throttle: deque of failure timestamps per (ip, email_lower).
# Cheap, single-process; fine for the current deployment shape.
_failures: dict[str, list[float]] = defaultdict(list)


def _throttle_key(ip: str, email: str) -> str:
    return f"{ip}|{email.lower()}"


def _check_throttle(ip: str, email: str) -> None:
    """Raise 429 if too many recent failures from this ip+email."""
    now = time.time()
    window = settings.login_window_seconds
    key = _throttle_key(ip, email)
    recent = [t for t in _failures[key] if now - t < window]
    _failures[key] = recent
    if len(recent) >= settings.login_max_attempts:
        wait = int(window - (now - recent[0]))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed logins. Try again in {max(wait, 30)}s.",
        )


def _record_failure(ip: str, email: str) -> None:
    _failures[_throttle_key(ip, email)].append(time.time())


def _clear_failures(ip: str, email: str) -> None:
    _failures.pop(_throttle_key(ip, email), None)


async def _safe_send(email: str, code: str) -> None:
    """Send the code, but never let an email failure break the request."""
    try:
        await send_otp_email(email, code)
    except Exception:
        logger.exception("Failed to send OTP email to %s", email)


def _issue_tokens(user: User) -> Token:
    return Token(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


async def _issue_otp(session: AsyncSession, user: User) -> str:
    """Replace any existing code for the user with a fresh one. Returns the code."""
    await session.execute(delete(EmailOTP).where(EmailOTP.user_id == user.id))
    code = generate_otp()
    otp = EmailOTP(
        user_id=user.id,
        code_hash=hash_otp(code),
        purpose="email_verify",
        expires_at=dt.datetime.now(dt.timezone.utc)
        + dt.timedelta(minutes=settings.otp_expire_minutes),
    )
    session.add(otp)
    await session.commit()
    return code


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate, session: SessionDep) -> RegisterResponse:
    email = data.email.lower()
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    user = User(
        email=email,
        hashed_password=hash_password(data.password),
        display_name=data.display_name,
        is_verified=False,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    code = await _issue_otp(session, user)
    await _safe_send(user.email, code)

    return RegisterResponse(
        message="Verification code sent. Check your email.",
        email=user.email,
        # Surface the code only in dev console mode for easy testing.
        dev_code=code if (settings.is_dev and settings.email_provider == "console") else None,
    )


@router.post("/verify-email", response_model=Token)
async def verify_email(data: VerifyEmailRequest, session: SessionDep) -> Token:
    email = data.email.lower()
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.is_verified:
        return _issue_tokens(user)

    otp = await session.scalar(
        select(EmailOTP).where(EmailOTP.user_id == user.id).order_by(EmailOTP.created_at.desc())
    )
    if otp is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No code found. Request a new one.")
    if otp.expires_at < dt.datetime.now(dt.timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Code expired. Request a new one.")
    if otp.attempts >= settings.otp_max_attempts:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts. Request a new code.")

    if not verify_otp(data.code, otp.code_hash):
        otp.attempts += 1
        await session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect code")

    user.is_verified = True
    await session.execute(delete(EmailOTP).where(EmailOTP.user_id == user.id))
    await session.commit()
    return _issue_tokens(user)


@router.post("/resend-otp", status_code=status.HTTP_202_ACCEPTED)
async def resend_otp(data: ResendRequest, session: SessionDep) -> dict[str, str | None]:
    user = await session.scalar(select(User).where(User.email == data.email.lower()))
    # Don't reveal whether the email exists.
    if user is None or user.is_verified:
        return {"message": "If that account needs verification, a code was sent.", "dev_code": None}
    code = await _issue_otp(session, user)
    await _safe_send(user.email, code)
    return {
        "message": "A new code was sent.",
        "dev_code": code if (settings.is_dev and settings.email_provider == "console") else None,
    }


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
) -> Token:
    ip = (request.client.host if request.client else "unknown") or "unknown"
    email = form.username.lower()
    _check_throttle(ip, email)  # raises 429 if too many recent failures
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(form.password, user.hashed_password):
        _record_failure(ip, email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password"
        )
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Email not verified"
        )
    _clear_failures(ip, email)
    return _issue_tokens(user)


@router.post("/refresh", response_model=Token)
async def refresh(data: RefreshRequest, session: SessionDep) -> Token:
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
    )
    try:
        payload = decode_token(data.refresh_token)
        if payload.get("type") != "refresh":
            raise invalid
        subject = payload.get("sub")
        if subject is None:
            raise invalid
    except jwt.PyJWTError:
        raise invalid

    user = await session.get(User, uuid.UUID(subject))
    if user is None or not user.is_active:
        raise invalid
    return _issue_tokens(user)
