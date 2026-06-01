"""Olwen's long-term memory engine.

One place that owns: embedding text, writing memories (with supersede-not-delete
conflict handling), and retrieving the right subset to inject into the prompt
(hybrid: semantic vector + recency + importance). Nothing here is on the chat
hot path except `build_memory_context`, which is a couple of indexed queries.

Design notes:
- "Never forget": we NEVER delete on conflict. A changed fact sets the old row's
  `superseded_by` to the new row. Old rows stay queryable via `recall(...)`.
- Embeddings come from Gemini `text-embedding-004` (768-dim). They're optional —
  every path degrades to keyword + recency if no embedding is available, so a
  missing/quota-limited Gemini key never breaks chat.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import uuid

import httpx
from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.core.security import decrypt_secret
from app.models.memory import EMBED_DIM, Memory

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
EMBED_MODEL = "gemini-embedding-001"  # 3072-dim native; we request 768 to match the column

VALID_TYPES = {"semantic", "episodic", "procedural"}

# How much we inject. Core = always-on identity; retrieved = query-relevant.
_CORE_N = 14
_RETRIEVED_N = 8


# ───────────────────────────── embeddings ──────────────────────────────────
async def embed_text(text: str, gemini_key: str | None, *, query: bool = False) -> list[float] | None:
    """Return a 768-dim embedding, or None if unavailable (never raises)."""
    if not gemini_key or not text.strip():
        return None
    task = "RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT"
    try:
        async with httpx.AsyncClient(timeout=12) as http:
            r = await http.post(
                f"{GEMINI_BASE}/models/{EMBED_MODEL}:embedContent",
                params={"key": gemini_key},
                json={
                    "model": f"models/{EMBED_MODEL}",
                    "content": {"parts": [{"text": text[:8000]}]},
                    "taskType": task,
                    "outputDimensionality": EMBED_DIM,
                },
            )
            r.raise_for_status()
            vals = (r.json().get("embedding") or {}).get("values")
            if isinstance(vals, list) and len(vals) == EMBED_DIM:
                return [float(x) for x in vals]
    except Exception:
        pass
    return None


# ───────────────────────────── write path ──────────────────────────────────
async def add_memory(
    session,
    user_id: uuid.UUID,
    content: str,
    *,
    mem_type: str = "semantic",
    subject: str | None = None,
    importance: int = 5,
    source: str = "extracted",
    gemini_key: str | None = None,
    commit: bool = True,
) -> Memory | None:
    """Insert a memory with supersede-on-conflict. Returns the new row (or the
    existing one if it was an exact duplicate). Never deletes."""
    content = (content or "").strip()
    if not content:
        return None
    if mem_type not in VALID_TYPES:
        mem_type = "semantic"
    importance = max(1, min(10, int(importance)))

    # active rows sharing the same subject are candidates for dedup/supersede
    active = list(await session.scalars(
        select(Memory).where(
            Memory.user_id == user_id,
            Memory.superseded_by.is_(None),
        )
    ))
    norm = content.casefold()
    for row in active:
        if (row.content or "").strip().casefold() == norm:
            return row  # exact duplicate — nothing to do

    new = Memory(
        user_id=user_id, content=content, mem_type=mem_type,
        subject=(subject or None), importance=importance, source=source,
    )
    vec = await embed_text(content, gemini_key)
    if vec is not None:
        new.embedding = vec
        new.embed_model = EMBED_MODEL
    session.add(new)
    await session.flush()  # assign new.id

    # supersede any active row with the SAME subject (a fact changed). Explicit
    # user memories also override prior extracted ones on the same subject.
    if subject:
        for row in active:
            same_subject = (row.subject or "").casefold() == subject.casefold()
            if same_subject and row.id != new.id:
                row.superseded_by = new.id

    if commit:
        await session.commit()
        await session.refresh(new)
    return new


# ─────────────────────────── retrieval (read) ──────────────────────────────
def _recency(created: dt.datetime | None) -> float:
    if not created:
        return 0.0
    now = dt.datetime.now(dt.timezone.utc)
    age_days = max(0.0, (now - created).total_seconds() / 86400.0)
    return math.exp(-age_days / 90.0)  # half-ish life ~2 months, ranking only


async def build_memory_context(
    session,
    user_id: uuid.UUID,
    query: str | None = None,
    gemini_key: str | None = None,
) -> list[str]:
    """Return the ranked subset of memory content strings to inject into the
    prompt: a small always-on CORE (identity/preferences) plus query-relevant
    RETRIEVED rows. Bumps access stats on what it returns."""
    active = list(await session.scalars(
        select(Memory).where(Memory.user_id == user_id, Memory.superseded_by.is_(None))
    ))
    if not active:
        return []

    # CORE — highest-importance identity facts, always present.
    core = sorted(active, key=lambda m: (m.importance, m.created_at or dt.datetime.min.replace(tzinfo=dt.timezone.utc)), reverse=True)[:_CORE_N]
    core_ids = {m.id for m in core}

    # RETRIEVED — rank the rest against the query.
    rest = [m for m in active if m.id not in core_ids]
    retrieved: list[Memory] = []
    if query and rest:
        qvec = await embed_text(query, gemini_key, query=True)
        if qvec is not None:
            # semantic: cosine distance over embedded rows; combine with recency+importance
            embedded = [m for m in rest if m.embedding is not None]
            def sim(m: Memory) -> float:
                d = _cosine_distance(qvec, m.embedding)  # 0..2, lower=closer
                rel = max(0.0, 1.0 - d)
                return 0.55 * rel + 0.25 * _recency(m.created_at) + 0.20 * (m.importance / 10.0)
            retrieved = sorted(embedded, key=sim, reverse=True)[:_RETRIEVED_N]
        if not retrieved:
            # keyword fallback (no embeddings or none embedded yet)
            toks = {t for t in _tokens(query) if len(t) > 2}
            def kw(m: Memory) -> float:
                hay = f"{m.subject or ''} {m.content}".casefold()
                overlap = sum(1 for t in toks if t in hay)
                return 0.45 * min(1.0, overlap / max(1, len(toks))) + 0.35 * _recency(m.created_at) + 0.20 * (m.importance / 10.0)
            ranked = sorted(rest, key=kw, reverse=True)
            retrieved = [m for m in ranked if kw(m) > 0.2][:_RETRIEVED_N]

    chosen = core + retrieved
    # bump access stats (fire-and-forget within this txn)
    ids = [m.id for m in chosen]
    if ids:
        await session.execute(
            update(Memory).where(Memory.id.in_(ids)).values(
                last_accessed=dt.datetime.now(dt.timezone.utc),
                access_count=Memory.access_count + 1,
            )
        )
        # Persist the access signal: the request session closes without a final
        # commit, so without this the bump rolls back and the signal stays inert.
        try:
            await session.commit()
        except Exception:
            await session.rollback()
    return [m.content for m in chosen]


async def recall(
    session,
    user_id: uuid.UUID,
    query: str,
    gemini_key: str | None = None,
    include_archived: bool = True,
    limit: int = 8,
) -> list[Memory]:
    """Search ALL memory (including superseded/archived rows) — this is how
    'what did I used to…' reaches old facts. Semantic if possible, else keyword."""
    stmt = select(Memory).where(Memory.user_id == user_id)
    if not include_archived:
        stmt = stmt.where(Memory.superseded_by.is_(None))
    rows = list(await session.scalars(stmt))
    if not rows or not query.strip():
        return rows[:limit]

    qvec = await embed_text(query, gemini_key, query=True)
    if qvec is not None and any(m.embedding is not None for m in rows):
        embedded = [m for m in rows if m.embedding is not None]
        embedded.sort(key=lambda m: _cosine_distance(qvec, m.embedding))
        return embedded[:limit]
    toks = {t for t in _tokens(query) if len(t) > 2}
    rows.sort(key=lambda m: sum(1 for t in toks if t in f"{m.subject or ''} {m.content}".casefold()), reverse=True)
    return rows[:limit]


# ───────────────────── background: auto-extraction ─────────────────────────
_EXTRACT_SYSTEM = (
    "You extract durable, long-term memories from a conversation between a user "
    "and their AI assistant. Output ONLY facts worth remembering for months: "
    "stable preferences, personal facts, important people/projects, decisions, "
    "and how the user likes to work. Ignore small talk, transient state, and "
    "anything the assistant said. If nothing is worth saving, return an empty list.\n\n"
    'Return STRICT JSON: {"memories":[{"content": str, "type": '
    '"semantic"|"episodic"|"procedural", "subject": str, "importance": 1-10}]} '
    "— subject is a short topic key (e.g. \"employer\", \"diet\", \"project:olwen\"). "
    "Keep each content one concise sentence in the third person about the user."
)


async def extract_memories_bg(user_id: uuid.UUID, recent_turns: list[dict], gemini_key: str | None) -> None:
    """Fire-and-forget after a chat turn: mine durable facts and store them.
    Opens its own session; failures are swallowed (never affects the user)."""
    if not gemini_key or not recent_turns:
        return
    convo = "\n".join(f"{t.get('role', '?')}: {t.get('content', '')}" for t in recent_turns[-6:])
    try:
        candidates = await _extract_via_gemini(convo, gemini_key)
    except Exception:
        return
    if not candidates:
        return
    try:
        async with SessionLocal() as session:
            for c in candidates[:8]:
                await add_memory(
                    session, user_id, c.get("content", ""),
                    mem_type=c.get("type", "semantic"),
                    subject=c.get("subject"),
                    importance=int(c.get("importance", 5) or 5),
                    source="extracted",
                    gemini_key=gemini_key,
                    commit=False,
                )
            await session.commit()
    except Exception:
        pass


async def _extract_via_gemini(convo: str, gemini_key: str) -> list[dict]:
    body = {
        "system_instruction": {"parts": [{"text": _EXTRACT_SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": convo}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.post(
            f"{GEMINI_BASE}/models/gemini-2.0-flash:generateContent",
            params={"key": gemini_key}, json=body,
        )
        r.raise_for_status()
        data = r.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        obj = json.loads(text)
        mems = obj.get("memories")
        return mems if isinstance(mems, list) else []
    except Exception:
        return []


async def backfill_embeddings(user_id: uuid.UUID, gemini_key: str | None, limit: int = 40) -> None:
    """One-shot: embed active rows that have no vector yet (legacy memories).
    Fire-and-forget; opens its own session."""
    if not gemini_key:
        return
    try:
        async with SessionLocal() as session:
            rows = list(await session.scalars(
                select(Memory).where(
                    Memory.user_id == user_id,
                    Memory.superseded_by.is_(None),
                    Memory.embedding.is_(None),
                ).limit(limit)
            ))
            changed = False
            for m in rows:
                vec = await embed_text(m.content, gemini_key)
                if vec is not None:
                    m.embedding = vec
                    m.embed_model = EMBED_MODEL
                    changed = True
            if changed:
                await session.commit()
    except Exception:
        pass


# ────────────────────────────── helpers ────────────────────────────────────
def _tokens(s: str) -> list[str]:
    return [t for t in "".join(c if c.isalnum() else " " for c in s.casefold()).split() if t]


def _cosine_distance(a: list[float], b: list[float] | None) -> float:
    if not b:
        return 2.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return 1.0 - (dot / (na * nb))


def gemini_key_for(user) -> str | None:
    """Decrypt the user's Gemini key (used for embeddings + extraction),
    independent of which provider they chat with."""
    enc = getattr(user, "gemini_key_enc", None)
    return decrypt_secret(enc) if enc else None
