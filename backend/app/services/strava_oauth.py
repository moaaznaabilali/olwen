"""Strava OAuth + activity fetch.

https://developers.strava.com/docs/authentication/
Free for personal use, rate-limited to 100 reqs / 15 min / 1000 daily.
"""
import datetime as dt
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings

SCOPES = ["read", "activity:read", "profile:read_all"]

_AUTH = "https://www.strava.com/oauth/authorize"
_TOKEN = "https://www.strava.com/oauth/token"
_API = "https://www.strava.com/api/v3"

REDIRECT_URI = "http://localhost:8000/api/strava/oauth/callback"


def build_auth_url(state: str, client_id: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": ",".join(SCOPES),
        "approval_prompt": "auto",
        "state": state,
    }
    return f"{_AUTH}?{urlencode(params)}"


def make_state(user_id: str) -> str:
    import jwt
    payload = {
        "sub": str(user_id),
        "nonce": secrets.token_urlsafe(8),
        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=15),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_state(state: str) -> str | None:
    import jwt
    try:
        return jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm]).get("sub")
    except Exception:
        return None


async def exchange_code(code: str, client_id: str, client_secret: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            _TOKEN,
            data={
                "client_id": client_id, "client_secret": client_secret,
                "code": code, "grant_type": "authorization_code",
            },
        )
        r.raise_for_status()
        return r.json()


async def refresh_access(refresh_token: str, client_id: str, client_secret: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            _TOKEN,
            data={
                "client_id": client_id, "client_secret": client_secret,
                "refresh_token": refresh_token, "grant_type": "refresh_token",
            },
        )
        r.raise_for_status()
        return r.json()


async def get_athlete(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{_API}/athlete", headers={"Authorization": f"Bearer {access_token}"})
        r.raise_for_status()
        return r.json()


async def recent_activities(access_token: str, limit: int = 8) -> list[dict]:
    """Newest `limit` activities. Normalised for the dashboard widget."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{_API}/athlete/activities",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"per_page": max(1, min(limit, 30))},
        )
        r.raise_for_status()
        rows = r.json()
    out: list[dict] = []
    for a in rows:
        dist_m = a.get("distance") or 0
        secs = a.get("moving_time") or 0
        out.append({
            "id": str(a.get("id", "")),
            "name": a.get("name") or a.get("type", "Activity"),
            "type": a.get("type") or "",                      # Run, Ride, Swim, Walk, etc.
            "sport_type": a.get("sport_type") or a.get("type") or "",
            "distance_km": round(dist_m / 1000, 2),
            "duration_min": round(secs / 60),
            "moving_pace": _pace_from(secs, dist_m, a.get("type", "")),
            "elevation_gain_m": round(a.get("total_elevation_gain") or 0),
            "average_heartrate": a.get("average_heartrate"),
            "start_date": a.get("start_date") or "",
        })
    return out


def _pace_from(secs: float, dist_m: float, kind: str) -> str:
    """Human pace: min/km for runs/walks, km/h for rides/swims."""
    if not secs or not dist_m:
        return ""
    if kind in ("Run", "Walk", "Hike", "TrailRun"):
        pace = secs / 60 / (dist_m / 1000)
        m, s = divmod(int(pace * 60), 60)
        return f"{m}:{s:02d} /km"
    if kind in ("Ride", "VirtualRide", "EBikeRide", "Velomobile"):
        kmh = (dist_m / 1000) / (secs / 3600)
        return f"{kmh:.1f} km/h"
    return ""
