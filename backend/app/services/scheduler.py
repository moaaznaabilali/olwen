"""The automation engine: a single async tick loop that fires user-defined
scheduled tasks. One Postgres table is the source of truth; `next_run` is the
durable cursor. Mirrors Olwen's existing pollers (telegram, whatsapp).

Safety properties:
- claim-by-row-lock (`FOR UPDATE SKIP LOCKED`) so a slow run never double-fires;
- misfire grace (don't blast a 7am brief at 2pm after downtime);
- next_run is ALWAYS recomputed from a fresh localized "now" (DST-safe);
- a failing action is recorded and surfaced to the user, never silent.
"""
from __future__ import annotations

import asyncio
import datetime as dt
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy import select, text

from app.core.database import SessionLocal
from app.core.security import decrypt_secret
from app.models.scheduled_task import ScheduledTask
from app.models.user import User

TICK_SECONDS = 30
MISFIRE_GRACE = dt.timedelta(hours=1)


# ─────────────────────────── schedule maths ────────────────────────────────
def daily_to_cron(hhmm: str) -> str:
    """'07:30' -> '30 7 * * *'."""
    h, m = (hhmm or "08:00").split(":")
    return f"{int(m)} {int(h)} * * *"


def compute_next_run(cron_expr: str, tz: str, after: dt.datetime | None = None) -> dt.datetime:
    """Next fire time in UTC. Always computed from a fresh localized now so DST
    transitions are handled by the tz database, not by forward-projecting."""
    try:
        zone = ZoneInfo(tz or "UTC")
    except Exception:
        zone = ZoneInfo("UTC")
    base = (after.astimezone(zone) if after else dt.datetime.now(zone))
    nxt = croniter(cron_expr, base).get_next(dt.datetime)
    if nxt.tzinfo is None:
        nxt = nxt.replace(tzinfo=zone)
    return nxt.astimezone(dt.timezone.utc)


# ──────────────────────────── the tick loop ────────────────────────────────
async def scheduler_loop() -> None:
    """Every TICK_SECONDS, run everything that's due. Never raises out."""
    while True:
        try:
            await _tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(TICK_SECONDS)


async def _tick() -> None:
    now = dt.datetime.now(dt.timezone.utc)
    async with SessionLocal() as session:
        # claim due rows; SKIP LOCKED means a concurrent/slow run can't be grabbed twice
        due = list(await session.scalars(
            select(ScheduledTask)
            .where(
                ScheduledTask.enabled.is_(True),
                ScheduledTask.next_run.isnot(None),
                ScheduledTask.next_run <= now,
            )
            .order_by(ScheduledTask.next_run)
            .with_for_update(skip_locked=True)
            .limit(20)
        ))
        for task in due:
            # misfire grace: too-late runs are skipped (don't replay a stale brief)
            if task.next_run and (now - task.next_run) > MISFIRE_GRACE:
                task.last_status = "skipped"
                task.next_run = compute_next_run(task.cron_expr, task.tz)
                continue
            # claim it: advance next_run + mark running, then COMMIT before the
            # (possibly slow) action so we don't hold the row lock across it.
            task.last_status = "running"
            task.next_run = compute_next_run(task.cron_expr, task.tz)
            tid = task.id
            await session.commit()
            asyncio.create_task(_run_one(tid))
        # Persist any skip-branch advances. Critical: an all-skip batch (e.g. the
        # machine was asleep past a daily time) has no fire-branch commit above,
        # so without this the advanced next_run rolls back and the task churns
        # as "due" forever, never firing again.
        await session.commit()


async def _run_one(task_id) -> None:
    """Execute one task in its own session/transaction and record the outcome."""
    started = dt.datetime.now(dt.timezone.utc)
    async with SessionLocal() as session:
        task = await session.get(ScheduledTask, task_id)
        if task is None:
            return
        user = await session.get(User, task.user_id)
        status, output, err = "ok", "", None
        try:
            output = await run_action(task, user, session)
            await _deliver(task, user, session, output)
        except Exception as exc:  # noqa: BLE001
            status, err = "error", str(exc)[:1000]
            await _notify_failure(task, user, session, err)
        finally:
            task.last_run = started
            task.last_status = status
            task.last_error = err
            task.last_output = (output or "")[:4000]
            task.last_duration_ms = int(
                (dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000
            )
            await session.commit()


# ──────────────────────────── actions ──────────────────────────────────────
async def run_action(task: ScheduledTask, user: User, session) -> str:
    """Produce the text payload for this task's action."""
    action = task.action or {}
    kind = action.get("type")

    if kind == "morning_brief":
        from app.services.brief import build_brief
        return (await build_brief(user, session)).get("narrative", "")

    if kind == "read_news":
        from app.services.news_brief import build_news_brief
        return (await build_news_brief(user, session)).get("narrative", "")

    if kind == "reminder":
        return str(action.get("text", "")).strip()

    if kind == "send_email":
        # literal body, or generate from a prompt via the user's chat provider
        body = str(action.get("body", "")).strip()
        if not body and action.get("prompt"):
            body = await _generate_text(user, str(action["prompt"]))
        return body

    if kind == "agent_goal":
        return await _run_agent_goal(user, session, str(action.get("goal", "")))

    if kind == "workflow":
        return await run_workflow(task, user, session, action.get("steps") or [])

    return ""


# ─────────────────────── multi-step workflows ──────────────────────────────
# A workflow is an ordered list of steps. A running "content" string flows
# through them: producer steps set it, sink steps consume it. This is what lets
# a normal user build "get the news → save it to a file → email it to me".
async def run_workflow(task: ScheduledTask, user: User, session, steps: list[dict]) -> str:
    content = ""          # the text flowing between steps
    log: list[str] = []   # human-readable per-step trace (stored as last_output)
    for i, step in enumerate(steps, 1):
        op = (step or {}).get("op", "")
        try:
            if op == "message":
                # literal text the user typed; {content} keeps any prior content
                content = str(step.get("text", "")).replace("{content}", content or "")
                log.append(f"{i}. Wrote a message")
            elif op == "morning_brief":
                from app.services.brief import build_brief
                content = (await build_brief(user, session)).get("narrative", "")
                log.append(f"{i}. Got morning brief")
            elif op == "read_news":
                from app.services.news_brief import build_news_brief
                content = (await build_news_brief(user, session)).get("narrative", "")
                log.append(f"{i}. Got the news")
            elif op == "ask_olwen":
                # {content} in the prompt is replaced with whatever flowed in so far,
                # so "summarise the news above" works.
                prompt = str(step.get("prompt", "")).replace("{content}", content or "")
                content = await _run_agent_goal(user, session, prompt) or await _generate_text(user, prompt)
                log.append(f"{i}. Asked Olwen")
            elif op == "save_file":
                path = _save_file(str(step.get("filename") or "olwen-output.txt"), content)
                log.append(f"{i}. Saved to {path}")
            elif op == "send_email":
                to = _recipients(step.get("to"), user)
                subject = str(step.get("subject") or task.name)
                await _send_email_to(user, session, to, subject, content or "(empty)")
                log.append(f"{i}. Emailed {', '.join(to)}")
            elif op == "send_telegram":
                await _send_telegram(user, content or "(empty)")
                log.append(f"{i}. Sent to Telegram")
            else:
                log.append(f"{i}. (skipped unknown step '{op}')")
        except Exception as exc:  # noqa: BLE001 — surface which step failed
            log.append(f"{i}. {op} FAILED: {exc}")
            raise RuntimeError("; ".join(log)) from exc
    return "\n".join(log)


def _recipients(raw, user: User) -> list[str]:
    if not raw:
        return [user.email]
    if isinstance(raw, str):
        return [a.strip() for a in raw.split(",") if a.strip()] or [user.email]
    return [str(a).strip() for a in raw if str(a).strip()] or [user.email]


def _save_file(filename: str, content: str) -> str:
    """Write content to a file under ~/Olwen (created if needed). Filename is
    sanitised (no path traversal); {date} expands to today; defaults to .txt."""
    import os
    base = os.path.expanduser("~/Olwen")
    os.makedirs(base, exist_ok=True)
    name = os.path.basename((filename or "").strip()) or "olwen-output.txt"
    name = name.replace("{date}", dt.datetime.now().strftime("%Y-%m-%d"))
    if not os.path.splitext(name)[1]:
        name += ".txt"
    path = os.path.join(base, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content or "")
    return path


async def _run_agent_goal(user: User, session, goal: str) -> str:
    """Run Olwen's agent headlessly for a scheduled goal. UI actions are ignored
    (no frontend is listening at 7am) — only the spoken result is delivered."""
    if not goal.strip():
        return ""
    from sqlalchemy import select as _select

    from app.core.config import settings
    from app.models.installed_skill import InstalledSkill
    from app.services.agent import build_tools, run_agent
    from app.services.memory import build_memory_context, gemini_key_for
    from app.services.olwen_ai import _build_system
    from app.services.skills import catalog_by_key

    gem = gemini_key_for(user)
    if not gem:
        return await _generate_text(user, goal)  # no tools available → plain reply
    installed = list(await session.scalars(
        _select(InstalledSkill.skill_key).where(InstalledSkill.user_id == user.id)
    ))
    cat = catalog_by_key()
    skills = [f"{cat[k]['name']} — {cat[k]['description']}" for k in installed if k in cat]
    memory = await build_memory_context(session, user.id, goal, gem)
    system = _build_system(memory, skills)
    tools = build_tools(installed)
    result = await run_agent(goal, [], gem, settings.gemini_model, system, tools, user, session)
    return (result.get("text") or "").strip()


async def _generate_text(user: User, prompt: str) -> str:
    """One-shot LLM completion via the user's chat provider (no tools)."""
    from app.services.olwen_ai import stream_reply
    enc = {"claude": user.llm_api_key_enc, "gemini": user.gemini_key_enc,
           "groq": user.groq_key_enc}.get(user.llm_provider or "")
    key = decrypt_secret(enc) if enc else None
    out = []
    async for delta in stream_reply(prompt, [], provider=user.llm_provider, api_key=key):
        out.append(delta)
    return "".join(out).strip()


# ──────────────────────────── delivery ─────────────────────────────────────
async def _deliver(task: ScheduledTask, user: User, session, output: str) -> None:
    # Workflows deliver via their own send_email/send_telegram steps — the
    # action-level channel would double-send, so skip it here.
    if (task.action or {}).get("type") == "workflow":
        return
    ch = task.notify_channel
    text_out = (output or "").strip()
    if not text_out:
        return
    if ch in ("telegram", "both"):
        await _send_telegram(user, text_out)
    if ch in ("email", "both"):
        await _send_email(task, user, session, text_out)
    # 'inapp' → nothing to push; last_output is stored for the UI to show.


async def _notify_failure(task: ScheduledTask, user: User, session, err: str) -> None:
    msg = f"Your automation “{task.name}” didn't run: {err}"
    try:
        if task.notify_channel in ("telegram", "both"):
            await _send_telegram(user, msg)
    except Exception:
        pass


async def _send_telegram(user: User, text_out: str) -> None:
    if not (user.telegram_token_enc and user.telegram_chat_id):
        return
    from app.services.telegram_bot import send_message
    await send_message(decrypt_secret(user.telegram_token_enc), user.telegram_chat_id, text_out)


async def _send_email_to(user: User, session, to: list[str], subject: str, body: str) -> None:
    """Send one email from the user's first connected account (provider-dispatched)."""
    from app.api.routes.email import _first_account, _send_for_account
    acc = await _first_account(user.id, session)
    if acc is None:
        raise RuntimeError("No email account is connected.")
    await _send_for_account(acc, session, to=to, subject=subject, body=body)


async def _send_email(task: ScheduledTask, user: User, session, text_out: str) -> None:
    action = task.action or {}
    to = _recipients(action.get("to"), user)
    subject = str(action.get("subject") or task.name)
    await _send_email_to(user, session, to, subject, text_out)


# expose for the migration / model registration
__all__ = ["scheduler_loop", "compute_next_run", "daily_to_cron"]
