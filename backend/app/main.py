"""Olwen backend — FastAPI application entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    apps as apps_routes,
    auth,
    devmode as devmode_routes,
    brief as brief_routes,
    calendar as calendar_routes,
    chat,
    computer as computer_routes,
    email as email_routes,
    github as github_routes,
    health,
    memory as memory_routes,
    news as news_routes,
    settings as settings_routes,
    skills as skills_routes,
    strava as strava_routes,
    tasks,
    users,
    voice as voice_routes,
)
from app.core.config import settings
from app.core.database import init_models


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dev convenience: ensure tables exist. Replace with Alembic migrations later.
    await init_models()
    yield


app = FastAPI(title=f"{settings.app_name} API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(settings_routes.router, prefix="/api/users/settings", tags=["settings"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(memory_routes.router, prefix="/api/memory", tags=["memory"])
app.include_router(skills_routes.router, prefix="/api/skills", tags=["skills"])
app.include_router(email_routes.router, prefix="/api/email", tags=["email"])
app.include_router(voice_routes.router, prefix="/api/voice", tags=["voice"])
app.include_router(github_routes.router, prefix="/api/github", tags=["github"])
app.include_router(calendar_routes.router, prefix="/api/calendar", tags=["calendar"])
app.include_router(news_routes.router, prefix="/api/news", tags=["news"])
app.include_router(brief_routes.router, prefix="/api/brief", tags=["brief"])
app.include_router(strava_routes.router, prefix="/api/strava", tags=["strava"])
app.include_router(apps_routes.router, prefix="/api/apps", tags=["apps"])
app.include_router(devmode_routes.router, prefix="/api/devmode", tags=["devmode"])
app.include_router(computer_routes.router, prefix="/api/computer", tags=["computer"])


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": f"{settings.entity_name} is awake."}
