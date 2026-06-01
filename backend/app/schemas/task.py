"""Task schemas."""
import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field


class TaskListCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class TaskListUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    position: int | None = None
    pos_x: int | None = None
    pos_y: int | None = None
    width: int | None = None
    collapsed: bool | None = None


class ListReorder(BaseModel):
    ids: list[uuid.UUID]


class TaskListRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    position: int = 0
    pos_x: int | None = None
    pos_y: int | None = None
    width: int | None = None
    collapsed: bool = False


class TaskCreate(BaseModel):
    list_id: uuid.UUID
    text: str = Field(min_length=1, max_length=400)
    priority: str = "med"
    due_date: dt.date | None = None
    tags: list[str] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    text: str | None = Field(default=None, max_length=400)
    priority: str | None = None
    done: bool | None = None
    list_id: uuid.UUID | None = None  # move a task to another list
    due_date: dt.date | None = None
    tags: list[str] | None = None
    clear_due: bool = False  # explicit clear, since due_date=None can't distinguish


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    list_id: uuid.UUID
    list_name: str
    text: str
    priority: str
    done: bool
    due_date: dt.date | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: dt.datetime
