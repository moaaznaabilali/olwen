"""Custom skill schemas."""
import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field


class CustomSkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=4, max_length=500)
    auth: str | None = Field(default=None, max_length=400)


class CustomSkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    url: str
    created_at: dt.datetime
