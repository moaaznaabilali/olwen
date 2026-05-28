"""News routes — topics catalog + topic-filtered feed."""
from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.services.news_brief import build_news_brief
from app.services.news_feeds import TOPICS, fetch_news

router = APIRouter()


@router.get("/topics")
async def list_topics() -> dict:
    """All topics the news feed knows about."""
    return {"topics": [
        {"key": k, "label": k.capitalize() if k != "ai" else "AI", "feed_count": len(v)}
        for k, v in TOPICS.items()
    ]}


@router.get("/feed")
async def feed(user: CurrentUser, limit: int = 12) -> dict:
    """User-specific news: filtered to their chosen topics, newest first.

    Defaults to AI + tech if the user hasn't picked anything yet.
    """
    chosen = list(user.news_topics or ["ai", "tech"])
    items = await fetch_news(chosen, per_topic=4, total=max(1, min(limit, 30)))
    return {"topics": chosen, "items": items}


@router.get("/brief")
async def brief(user: CurrentUser, session: SessionDep) -> dict:
    """Olwen's curated news brief — top 3-5 stories with one-line commentary
    each, plus a spoken narrative."""
    return await build_news_brief(user, session)
