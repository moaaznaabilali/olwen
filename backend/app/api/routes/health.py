"""Health / liveness endpoint."""
from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "entity": settings.entity_name,
        "environment": settings.environment,
    }
