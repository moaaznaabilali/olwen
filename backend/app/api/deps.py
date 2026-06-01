"""Shared API dependencies."""
import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_token
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: SessionDep,
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise credentials_exc
        subject = payload.get("sub")
        if subject is None:
            raise credentials_exc
    except jwt.PyJWTError:
        raise credentials_exc

    user = await session.get(User, uuid.UUID(subject))
    if user is None or not user.is_active:
        raise credentials_exc
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_user_id(token: Annotated[str, Depends(oauth2_scheme)]) -> uuid.UUID:
    """Authenticate from the signed JWT WITHOUT opening a DB session. Use this for
    long-lived / streaming endpoints (e.g. SSE), where holding a session for the
    request's whole lifetime would keep a transaction open and block migrations."""
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("type") != "access" or payload.get("sub") is None:
            raise exc
        return uuid.UUID(str(payload["sub"]))
    except (jwt.PyJWTError, ValueError):
        raise exc


CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]
