"""Task schemas."""
import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field


class TaskListCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class TaskListRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str


class TaskCreate(BaseModel):
    list_id: uuid.UUID
    text: str = Field(min_length=1, max_length=400)
    priority: str = "med"


class TaskUpdate(BaseModel):
    text: str | None = Field(default=None, max_length=400)
    priority: str | None = None
    done: bool | None = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    list_id: uuid.UUID
    list_name: str
    text: str
    priority: str
    done: bool
    created_at: dt.datetime
