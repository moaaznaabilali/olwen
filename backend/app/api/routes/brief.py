"""Morning brief — aggregate the day-ahead into a narrative Olwen speaks."""
import datetime as dt

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, SessionDep
from app.services.brief import build_brief

router = APIRouter()


class BriefPrefsRequest(BaseModel):
    enabled: bool | None = None
    time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


@router.get("/today")
async def today(user: CurrentUser, session: SessionDep) -> dict:
    """Generate the brief on demand. Doesn't update `brief_last_shown`."""
    return await build_brief(user, session)


@router.post("/today/seen")
async def mark_seen(user: CurrentUser, session: SessionDep) -> dict:
    """Record that the user has seen today's brief — so the dashboard's
    auto-trigger doesn't fire it again until tomorrow."""
    user.brief_last_shown = dt.datetime.now(dt.timezone.utc)
    await session.commit()
    return {"ok": True}


@router.get("/should-show")
async def should_show(user: CurrentUser) -> dict:
    """Has today's brief been shown? Drives the auto-trigger on dashboard mount."""
    if not user.brief_enabled:
        return {"show": False, "reason": "disabled"}
    now = dt.datetime.now()
    # Parse "HH:MM"
    try:
        hh, mm = (int(x) for x in user.brief_time.split(":"))
    except Exception:
        hh, mm = 8, 0
    brief_local = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if now < brief_local:
        return {"show": False, "reason": "too early", "scheduled_for": brief_local.isoformat()}
    last = user.brief_last_shown
    if last is not None and last.date() >= now.date():
        return {"show": False, "reason": "already shown today"}
    return {"show": True}


@router.put("/prefs")
async def update_prefs(data: BriefPrefsRequest, user: CurrentUser, session: SessionDep) -> dict:
    if data.enabled is not None:
        user.brief_enabled = data.enabled
    if data.time is not None:
        user.brief_time = data.time
    await session.commit()
    return {"enabled": user.brief_enabled, "time": user.brief_time}
