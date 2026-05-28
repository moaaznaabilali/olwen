"""Pydantic schemas for auth and users."""
import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str | None
    is_active: bool
    is_verified: bool
    created_at: dt.datetime


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterResponse(BaseModel):
    """Returned after register — verification required before login."""
    message: str
    email: EmailStr
    # Only populated in dev/console mode so you can test without real email.
    dev_code: str | None = None


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=8)


class ResendRequest(BaseModel):
    email: EmailStr


class ProviderState(BaseModel):
    connected: bool
    key_masked: str | None
    model: str


class VoiceState(BaseModel):
    enabled: bool
    lang: str


class WidgetEntry(BaseModel):
    key: str
    name: str
    column: str
    live: bool
    description: str
    glyph: str
    color: str
    core: bool = False


class SettingsRead(BaseModel):
    """What the Settings screen shows — never the raw key."""
    active_provider: str | None
    claude: ProviderState
    gemini: ProviderState
    groq: ProviderState
    voice: VoiceState
    auto_mark_read: bool = False
    dashboard_widgets: list[str] = []
    news_topics: list[str] = []
    widget_catalog: list[WidgetEntry] = []


class UpdateVoiceRequest(BaseModel):
    enabled: bool | None = None
    lang: str | None = Field(default=None, max_length=8)


class UpdateEmailPrefsRequest(BaseModel):
    auto_mark_read: bool | None = None


class UpdateDashboardRequest(BaseModel):
    widgets: list[str] | None = None        # list of widget keys to show


class UpdateNewsRequest(BaseModel):
    topics: list[str] | None = None         # list of news topic keys


class ConnectKeyRequest(BaseModel):
    api_key: str = Field(min_length=10, max_length=400)


class SelectProviderRequest(BaseModel):
    provider: str  # 'claude' | 'gemini'
