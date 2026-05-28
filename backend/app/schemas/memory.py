"""Memory schemas."""
import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=500)


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    content: str
    created_at: dt.datetime
