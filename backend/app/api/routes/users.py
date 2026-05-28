"""User routes."""
from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.models.user import User
from app.schemas.user import UserRead

router = APIRouter()


@router.get("/me", response_model=UserRead)
async def read_me(user: CurrentUser) -> User:
    return user
