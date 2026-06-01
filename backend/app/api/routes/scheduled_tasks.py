"""Scheduled tasks / automations — user-defined recurring workflows."""
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.models.scheduled_task import ScheduledTask
from app.schemas.scheduled_task import (
    ACTION_TYPES,
    CHANNELS,
    WORKFLOW_OPS,
    ScheduledTaskCreate,
    ScheduledTaskRead,
    ScheduledTaskUpdate,
)
from app.services.scheduler import compute_next_run, daily_to_cron, run_action, _deliver

router = APIRouter()


def _resolve_cron(kind: str, daily_time: str | None, cron_expr: str | None) -> str:
    if kind == "cron":
        if not cron_expr:
            raise HTTPException(status_code=400, detail="cron_expr is required for a cron schedule.")
        return cron_expr
    return daily_to_cron(daily_time or "08:00")


def _validate_action(action: dict) -> None:
    t = (action or {}).get("type")
    if t not in ACTION_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown action type. One of: {sorted(ACTION_TYPES)}")
    if t == "reminder" and not str(action.get("text", "")).strip():
        raise HTTPException(status_code=400, detail="A reminder needs 'text'.")
    if t == "agent_goal" and not str(action.get("goal", "")).strip():
        raise HTTPException(status_code=400, detail="An agent_goal needs 'goal'.")
    if t == "send_email" and not (str(action.get("body", "")).strip() or str(action.get("prompt", "")).strip()):
        raise HTTPException(status_code=400, detail="send_email needs 'body' or 'prompt'.")
    if t == "workflow":
        steps = action.get("steps")
        if not isinstance(steps, list) or not steps:
            raise HTTPException(status_code=400, detail="A workflow needs at least one step.")
        for s in steps:
            op = (s or {}).get("op")
            if op not in WORKFLOW_OPS:
                raise HTTPException(status_code=400, detail=f"Unknown workflow step '{op}'. One of: {sorted(WORKFLOW_OPS)}")


async def _owned(task_id: uuid.UUID, user_id, session: SessionDep) -> ScheduledTask:
    t = await session.get(ScheduledTask, task_id)
    if t is None or t.user_id != user_id:
        raise HTTPException(status_code=404, detail="Automation not found.")
    return t


@router.get("", response_model=list[ScheduledTaskRead])
async def list_tasks(user: CurrentUser, session: SessionDep) -> list[ScheduledTask]:
    rows = await session.scalars(
        select(ScheduledTask).where(ScheduledTask.user_id == user.id).order_by(ScheduledTask.created_at)
    )
    return list(rows)


@router.post("", response_model=ScheduledTaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(data: ScheduledTaskCreate, user: CurrentUser, session: SessionDep) -> ScheduledTask:
    _validate_action(data.action)
    if data.notify_channel not in CHANNELS:
        raise HTTPException(status_code=400, detail=f"notify_channel must be one of {sorted(CHANNELS)}")
    cron = _resolve_cron(data.schedule_kind, data.daily_time, data.cron_expr)
    t = ScheduledTask(
        user_id=user.id, name=data.name, action=data.action,
        schedule_kind=data.schedule_kind, cron_expr=cron, daily_time=data.daily_time,
        tz=data.tz, notify_channel=data.notify_channel, enabled=data.enabled,
        next_run=compute_next_run(cron, data.tz),
    )
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return t


@router.patch("/{task_id}", response_model=ScheduledTaskRead)
async def update_task(
    task_id: uuid.UUID, data: ScheduledTaskUpdate, user: CurrentUser, session: SessionDep
) -> ScheduledTask:
    t = await _owned(task_id, user.id, session)
    if data.action is not None:
        _validate_action(data.action)
        t.action = data.action
    if data.name is not None:
        t.name = data.name
    if data.notify_channel is not None:
        if data.notify_channel not in CHANNELS:
            raise HTTPException(status_code=400, detail="bad notify_channel")
        t.notify_channel = data.notify_channel
    if data.tz is not None:
        t.tz = data.tz
    if data.enabled is not None:
        t.enabled = data.enabled
    # recompute schedule if any timing field changed
    if any(v is not None for v in (data.schedule_kind, data.daily_time, data.cron_expr, data.tz)):
        t.schedule_kind = data.schedule_kind or t.schedule_kind
        if data.daily_time is not None:
            t.daily_time = data.daily_time
        t.cron_expr = _resolve_cron(t.schedule_kind, t.daily_time, data.cron_expr or t.cron_expr)
        t.next_run = compute_next_run(t.cron_expr, t.tz)
    await session.commit()
    await session.refresh(t)
    return t


@router.post("/{task_id}/toggle", response_model=ScheduledTaskRead)
async def toggle_task(task_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> ScheduledTask:
    t = await _owned(task_id, user.id, session)
    t.enabled = not t.enabled
    if t.enabled:
        t.next_run = compute_next_run(t.cron_expr, t.tz)
    await session.commit()
    await session.refresh(t)
    return t


@router.post("/{task_id}/run-now", response_model=ScheduledTaskRead)
async def run_now(task_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> ScheduledTask:
    """Execute immediately (for testing an automation), without disturbing its schedule."""
    import datetime as dt
    t = await _owned(task_id, user.id, session)
    u = user
    try:
        output = await run_action(t, u, session)
        await _deliver(t, u, session, output)
        t.last_status, t.last_error, t.last_output = "ok", None, (output or "")[:4000]
    except Exception as exc:  # noqa: BLE001
        t.last_status, t.last_error = "error", str(exc)[:1000]
    t.last_run = dt.datetime.now(dt.timezone.utc)
    await session.commit()
    await session.refresh(t)
    return t


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    t = await _owned(task_id, user.id, session)
    await session.delete(t)
    await session.commit()
