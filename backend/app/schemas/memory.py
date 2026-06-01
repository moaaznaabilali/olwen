"""Memory schemas."""
import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    mem_type: str = "semantic"
    subject: str | None = Field(default=None, max_length=120)
    importance: int = Field(default=6, ge=1, le=10)


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    content: str
    mem_type: str = "semantic"
    importance: int = 5
    subject: str | None = None
    source: str = "extracted"
    superseded_by: uuid.UUID | None = None
    access_count: int = 0
    last_accessed: dt.datetime | None = None
    created_at: dt.datetime
