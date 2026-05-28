"""Tiny RSS-backed news aggregator with topic filtering.

Each topic maps to a set of feeds. We fetch in parallel and merge.
No API keys needed.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import html
import re
from dataclasses import dataclass
from typing import Iterable

import feedparser
import httpx

TOPICS = {
    "ai":         ["https://www.technologyreview.com/feed/",
                   "https://venturebeat.com/category/ai/feed/",
                   "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"],
    "tech":       ["https://techcrunch.com/feed/",
                   "https://www.theverge.com/rss/index.xml",
                   "https://hnrss.org/frontpage"],
    "finance":    ["https://feeds.bloomberg.com/markets/news.rss",
                   "https://www.cnbc.com/id/100003114/device/rss/rss.html",
                   "https://www.ft.com/?format=rss"],
    "world":      ["https://feeds.reuters.com/reuters/worldNews",
                   "http://feeds.bbci.co.uk/news/world/rss.xml"],
    "science":    ["https://www.sciencedaily.com/rss/all.xml",
                   "https://www.nature.com/nature.rss"],
    "sports":     ["https://www.espn.com/espn/rss/news"],
    "health":     ["https://www.healthline.com/rss",
                   "https://medlineplus.gov/groupfeeds/new/news.xml"],
    "design":     ["https://abduzeedo.com/feed",
                   "https://www.smashingmagazine.com/feed/"],
    "startups":   ["https://news.ycombinator.com/rss",
                   "https://feeds.feedburner.com/TechCrunch/startups"],
}

TAG_FOR = {
    "ai": "AI", "tech": "Tech", "finance": "Finance", "world": "World",
    "science": "Science", "sports": "Sports", "health": "Health",
    "design": "Design", "startups": "Startups",
}


@dataclass
class NewsItem:
    title: str
    source: str
    url: str
    published: str               # ISO datetime
    tag: str                     # the topic this came from

    def as_dict(self) -> dict:
        return {
            "title": self.title, "source": self.source, "url": self.url,
            "published": self.published, "tag": self.tag,
        }


def _strip_html(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


async def _fetch_one(client: httpx.AsyncClient, url: str, topic: str, limit: int) -> list[NewsItem]:
    try:
        r = await client.get(url, headers={"User-Agent": "OlwenNews/1.0"})
        if r.status_code != 200:
            return []
        feed = feedparser.parse(r.text)
        source = (feed.feed.get("title") or url).strip()
        out: list[NewsItem] = []
        for e in feed.entries[: limit * 2]:
            title = _strip_html(e.get("title", ""))
            if not title:
                continue
            link = e.get("link", "")
            pub = ""
            for k in ("published", "updated", "created"):
                if e.get(k):
                    pub = e.get(k)
                    break
            # Normalise to ISO if feedparser parsed a tuple
            if hasattr(e, "published_parsed") and e.published_parsed:
                try:
                    pub = dt.datetime(*e.published_parsed[:6], tzinfo=dt.timezone.utc).isoformat()
                except Exception:
                    pass
            out.append(NewsItem(
                title=title[:180], source=source[:60], url=link,
                published=pub or "", tag=TAG_FOR.get(topic, topic.upper()),
            ))
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


async def fetch_news(topics: Iterable[str], per_topic: int = 4, total: int = 12) -> list[dict]:
    """Aggregate news across the requested topics, newest first."""
    topics = [t for t in topics if t in TOPICS]
    if not topics:
        topics = ["ai", "tech"]
    feeds: list[tuple[str, str]] = []
    for t in topics:
        for url in TOPICS[t]:
            feeds.append((t, url))

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        results = await asyncio.gather(*(_fetch_one(client, url, t, per_topic) for t, url in feeds))

    items: list[NewsItem] = [it for sub in results for it in sub]

    # Sort by published desc when we have dates; otherwise preserve order.
    def _key(it: NewsItem) -> str:
        return it.published or ""
    items.sort(key=_key, reverse=True)

    # De-dupe by title
    seen: set[str] = set()
    out: list[NewsItem] = []
    for it in items:
        k = it.title.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
        if len(out) >= total:
            break
    return [it.as_dict() for it in out]
