"""Email schemas."""
import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class EmailAccountCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=4, max_length=200)
    imap_host: str | None = None
    imap_port: int = 993
    smtp_host: str | None = None
    smtp_port: int = 587


class EmailAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr
    provider: str
    imap_host: str | None
    smtp_host: str | None
    created_at: dt.datetime


class EmailMessage(BaseModel):
    uid: str
    sender: str
    subject: str
    snippet: str
    date: str
    unread: bool


class TriagedEmail(EmailMessage):
    priority: str = "low"  # high | med | low
    suggestion: str = ""


class TriageResponse(BaseModel):
    emails: list[TriagedEmail]


class EmailFull(BaseModel):
    uid: str
    sender: str
    subject: str
    body: str
    date: str
    unread: bool


class EmailAction(BaseModel):
    """Something Olwen suggests doing about this email."""
    label: str                       # 2–4 words, imperative
    kind: str                        # 'open_url' | 'reply' | 'reminder' | 'task'
    payload: str = ""                # URL for open_url; date/time hint for reminder; etc.
    description: str = ""            # ≤ 12 words, what doing this means


class EmailSummary(BaseModel):
    uid: str
    summary: str                     # ≤ 3 sentences, what the email says + what to do
    actions: list[EmailAction] = []


class ComposeRequest(BaseModel):
    to: list[EmailStr]
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)


class ReplyRequest(BaseModel):
    body: str = Field(min_length=1, max_length=20000)


class DraftReplyResponse(BaseModel):
    draft: str                       # AI-generated reply body
    subject: str                     # auto-prefixed with "Re: " if needed


class SendResponse(BaseModel):
    ok: bool
    message_id: str = ""
