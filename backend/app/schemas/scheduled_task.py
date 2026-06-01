"""Scheduled-task (automation) schemas."""
import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

ACTION_TYPES = {"morning_brief", "read_news", "send_email", "agent_goal", "reminder", "workflow"}
# ops a workflow step may use
WORKFLOW_OPS = {"message", "morning_brief", "read_news", "ask_olwen", "save_file", "send_email", "send_telegram"}
CHANNELS = {"email", "telegram", "both", "inapp"}


class ScheduledTaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    action: dict  # {type: ..., ...}
    schedule_kind: str = "daily"  # 'daily' | 'cron'
    daily_time: str | None = Field(default="08:00", max_length=5)  # HH:MM when daily
    cron_expr: str | None = Field(default=None, max_length=120)    # required when cron
    tz: str = "UTC"
    notify_channel: str = "inapp"
    enabled: bool = True


class ScheduledTaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    action: dict | None = None
    schedule_kind: str | None = None
    daily_time: str | None = Field(default=None, max_length=5)
    cron_expr: str | None = Field(default=None, max_length=120)
    tz: str | None = None
    notify_channel: str | None = None
    enabled: bool | None = None


class ScheduledTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    action: dict
    schedule_kind: str
    cron_expr: str
    daily_time: str | None = None
    tz: str
    notify_channel: str
    enabled: bool
    next_run: dt.datetime | None = None
    last_run: dt.datetime | None = None
    last_status: str | None = None
    last_error: str | None = None
    last_output: str | None = None
    last_duration_ms: int | None = None
    created_at: dt.datetime
