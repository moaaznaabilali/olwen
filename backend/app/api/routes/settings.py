"""User settings — connect Claude or Gemini and pick which Olwen uses."""
from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings as app_settings
from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.models.user import User
from app.schemas.user import (
    ConnectKeyRequest,
    ProviderState,
    SelectProviderRequest,
    SettingsRead,
    UpdateDashboardRequest,
    UpdateEmailPrefsRequest,
    UpdateNewsRequest,
    UpdateVoiceRequest,
    VoiceState,
    WidgetEntry,
)
from app.services.olwen_ai import validate_key
from app.services.widget_catalog import WIDGETS, default_for_user

router = APIRouter()

PROVIDERS = ("claude", "gemini", "groq")
_MODELS = {
    "claude": lambda: app_settings.anthropic_model,
    "gemini": lambda: app_settings.gemini_model,
    "groq": lambda: app_settings.groq_model,
}


def _key_enc(user: User, provider: str) -> str | None:
    return {
        "claude": user.llm_api_key_enc,
        "gemini": user.gemini_key_enc,
        "groq": user.groq_key_enc,
    }[provider]


def _set_key_enc(user: User, provider: str, value: str | None) -> None:
    if provider == "claude":
        user.llm_api_key_enc = value
    elif provider == "gemini":
        user.gemini_key_enc = value
    else:
        user.groq_key_enc = value


def _provider_state(user: User, provider: str) -> ProviderState:
    enc = _key_enc(user, provider)
    return ProviderState(
        connected=enc is not None,
        key_masked=mask_secret(decrypt_secret(enc)) if enc else None,
        model=_MODELS[provider](),
    )


def _read(user: User) -> SettingsRead:
    return SettingsRead(
        active_provider=user.llm_provider,
        claude=_provider_state(user, "claude"),
        gemini=_provider_state(user, "gemini"),
        groq=_provider_state(user, "groq"),
        voice=VoiceState(enabled=user.voice_enabled, lang=user.voice_lang),
        auto_mark_read=user.auto_mark_read,
        dashboard_widgets=list(user.dashboard_widgets) if user.dashboard_widgets is not None else default_for_user(),
        news_topics=list(user.news_topics) if user.news_topics is not None else ["ai", "tech"],
        widget_catalog=[WidgetEntry(**w) for w in WIDGETS],
    )


def _check_provider(provider: str) -> None:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown provider")


@router.get("", response_model=SettingsRead)
async def get_settings(user: CurrentUser) -> SettingsRead:
    return _read(user)


# NOTE: declared before "/{provider}" so it isn't swallowed by the path param.
@router.put("/voice", response_model=SettingsRead)
async def update_voice(
    data: UpdateVoiceRequest, user: CurrentUser, session: SessionDep
) -> SettingsRead:
    if data.enabled is not None:
        user.voice_enabled = data.enabled
    if data.lang is not None:
        user.voice_lang = data.lang
    await session.commit()
    await session.refresh(user)
    return _read(user)


@router.put("/email", response_model=SettingsRead)
async def update_email_prefs(
    data: UpdateEmailPrefsRequest, user: CurrentUser, session: SessionDep
) -> SettingsRead:
    if data.auto_mark_read is not None:
        user.auto_mark_read = data.auto_mark_read
    await session.commit()
    await session.refresh(user)
    return _read(user)


@router.put("/dashboard", response_model=SettingsRead)
async def update_dashboard(
    data: UpdateDashboardRequest, user: CurrentUser, session: SessionDep
) -> SettingsRead:
    if data.widgets is not None:
        valid = {w["key"] for w in WIDGETS}
        # 'tasks' is core — always include even if user tries to disable it
        filtered = [k for k in data.widgets if k in valid]
        if "tasks" not in filtered:
            filtered.insert(0, "tasks")
        user.dashboard_widgets = filtered
    await session.commit()
    await session.refresh(user)
    return _read(user)


@router.put("/news", response_model=SettingsRead)
async def update_news(
    data: UpdateNewsRequest, user: CurrentUser, session: SessionDep
) -> SettingsRead:
    if data.topics is not None:
        from app.services.news_feeds import TOPICS
        user.news_topics = [t for t in data.topics if t in TOPICS]
    await session.commit()
    await session.refresh(user)
    return _read(user)


@router.put("/{provider}", response_model=SettingsRead)
async def connect_provider(
    provider: str, data: ConnectKeyRequest, user: CurrentUser, session: SessionDep
) -> SettingsRead:
    _check_provider(provider)
    key = data.api_key.strip()
    if not await validate_key(provider, key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That key didn't work — check it and try again.",
        )
    _set_key_enc(user, provider, encrypt_secret(key))
    user.llm_provider = provider  # connecting makes it the active brain
    await session.commit()
    await session.refresh(user)
    return _read(user)


@router.delete("/{provider}", response_model=SettingsRead)
async def disconnect_provider(
    provider: str, user: CurrentUser, session: SessionDep
) -> SettingsRead:
    _check_provider(provider)
    _set_key_enc(user, provider, None)
    if user.llm_provider == provider:
        # fall back to any other still-connected provider
        user.llm_provider = next(
            (p for p in PROVIDERS if p != provider and _key_enc(user, p)), None
        )
    await session.commit()
    await session.refresh(user)
    return _read(user)


@router.put("", response_model=SettingsRead)
async def select_provider(
    data: SelectProviderRequest, user: CurrentUser, session: SessionDep
) -> SettingsRead:
    _check_provider(data.provider)
    if _key_enc(user, data.provider) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Connect that provider's key first.",
        )
    user.llm_provider = data.provider
    await session.commit()
    await session.refresh(user)
    return _read(user)
