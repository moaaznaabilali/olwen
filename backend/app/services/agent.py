"""Tool-using agent loop (Gemini).

Lets Olwen actually RUN skills via function-calling. Tools exposed to the model
are built dynamically from the user's installed skills (e.g. Tasks, Web Search).
Other providers/skills follow this same pattern.
"""
import asyncio
import os
import pathlib
from collections.abc import AsyncIterator

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decrypt_secret
from app.models.task import Task, TaskList
from app.models.user import User

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# ---- tool declarations (Gemini functionDeclarations) ----
_TASK_DECLS = [
    {"name": "list_tasks", "description": "List the user's current OPEN (not done) tasks.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "add_task", "description": "Create a new task for the user.",
     "parameters": {"type": "object", "properties": {
         "text": {"type": "string", "description": "the task description"}}, "required": ["text"]}},
    {"name": "complete_task", "description": "Mark a task as done by matching part of its text.",
     "parameters": {"type": "object", "properties": {
         "text": {"type": "string", "description": "words from the task to complete"}}, "required": ["text"]}},
]
_SEARCH_DECL = {
    "name": "web_search",
    "description": "Search the web for current information. Use when the user asks about facts, news, or anything you need to look up.",
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string", "description": "the search query"}}, "required": ["query"]},
}

# ---- long-term memory tools ----
_MEMORY_DECLS = [
    {
        "name": "remember",
        "description": (
            "Save a durable, long-term memory about the user when they share something "
            "worth keeping for months — a stable preference, a personal fact, an important "
            "person or project, or how they like to work. Don't save small talk or transient state."
        ),
        "parameters": {"type": "object", "properties": {
            "content": {"type": "string", "description": "One concise sentence about the user, third person."},
            "type": {"type": "string", "description": "semantic (facts/preferences), episodic (events), or procedural (how they work)."},
            "subject": {"type": "string", "description": "Short topic key for this fact, e.g. 'employer', 'diet', 'project:olwen'. Lets a newer fact replace an older one on the same subject."},
            "importance": {"type": "integer", "description": "1-10, how important to remember. Default 7."},
        }, "required": ["content"]},
    },
    {
        "name": "recall_memory",
        "description": (
            "Search everything you've ever remembered about the user — including older, "
            "superseded facts — to answer 'what did I used to…', 'do you remember…', or to "
            "ground a reply in their history."
        ),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "what to recall"}}, "required": ["query"]},
    },
]

# ---- UI action tools ----
# These let Olwen actually open surfaces inside himself when the user asks.
# Each one returns a `ui_action` payload that the frontend dispatches. The LLM
# gets a brief success message back so it can continue the conversation.
_UI_DECLS = [
    {
        "name": "open_terminal",
        "description": (
            "Open the Terminal app on the dashboard so the user can run shell commands "
            "(claude, git, npm, etc.). Use when the user asks to open a terminal, start work, "
            "run something in the shell, or launch claude code."
        ),
        "parameters": {"type": "object", "properties": {
            "cwd": {"type": "string", "description": "Optional directory to start the shell in (absolute path)."},
            "command": {"type": "string", "description": "Optional command to run automatically after the shell starts (e.g. 'claude --dangerously-skip-permissions')."},
        }},
    },
    {
        "name": "open_dev_mode",
        "description": (
            "Open the Dev Mode PICKER — black focus screen with a project list the user "
            "browses. Use ONLY when the user wants to browse / explore / 'show me my projects' "
            "without naming or implying one. If they say 'open a project', 'any project', "
            "'start working on X', or 'open X with claude' — use open_project instead."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "list_projects",
        "description": (
            "Return the user's local git projects (newest first). Useful before "
            "open_project when the user's match string is ambiguous — you can mention "
            "candidates back to them."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "open_dev_studio",
        "description": (
            "Open DEV STUDIO — a live, split-screen coding workspace: two project terminals "
            "side by side (each running Claude Code), the Olwen creature, and a live rail "
            "showing the project's tasks and the latest pushes to the repo. Use when the user "
            "says 'let's code', 'let's build', 'start a coding session', 'open my projects to "
            "work', or names TWO projects to work on together. Pass up to two project name "
            "hints in `projects`; if omitted, the two most recently modified projects are used."
        ),
        "parameters": {"type": "object", "properties": {
            "projects": {"type": "array", "items": {"type": "string"},
                         "description": "Up to two project name hints to open side by side."},
        }},
    },
    {
        "name": "queue_dev_job",
        "description": (
            "Queue an UNATTENDED coding job: Olwen runs Claude Code on the goal in a "
            "local project, on a fresh branch behind safety guardrails, opens a pull "
            "request, and pings you when done. Use when the user says 'run a job', "
            "'fix X in <project> while I'm away', 'build Y in <project>', etc. Great "
            "from Telegram. Give the project name hint and a clear goal."
        ),
        "parameters": {"type": "object", "properties": {
            "project": {"type": "string", "description": "project name hint (which repo)"},
            "goal": {"type": "string", "description": "what to build or fix"},
        }, "required": ["goal"]},
    },
    {
        "name": "open_project",
        "description": (
            "Open one specific local project directly: pops Finder, opens a terminal cd'd into "
            "the project folder, and (by default) auto-runs `claude --dangerously-skip-permissions` "
            "inside it. This is THE tool to use whenever the user says 'open a project', 'open X', "
            "'any project', 'start working', 'start work with claude', or names a project. "
            "If `match` is empty, the most recently modified project is chosen."
        ),
        "parameters": {"type": "object", "properties": {
            "match": {"type": "string", "description": "Partial project name to match (case-insensitive). Leave empty for newest."},
            "with_claude": {"type": "boolean", "description": "Run claude in dangerous-skip-permissions mode after the shell starts. Default true."},
        }},
    },
    {
        "name": "open_settings",
        "description": "Open the Settings (Console) screen. Use when the user wants to change a setting, configure something, or connect/disconnect an account.",
        "parameters": {"type": "object", "properties": {
            "section": {"type": "string", "description": "Which tab to open: 'connections' | 'dashboard' | 'voice' | 'email' | 'news' | 'memory' | 'skills'"},
        }},
    },
    {
        "name": "open_compose_email",
        "description": "Open the email composer for a new outgoing email. Use when the user asks to send/write/compose an email.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "run_morning_brief",
        "description": "Run the morning brief cinematic — Olwen reads weather, calendar, tasks, inbox, and news aloud. Use when the user asks for a brief, summary of the day, what's ahead.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "read_news",
        "description": "Open the news brief cinematic — Olwen picks the top stories and reads them aloud. Use when the user asks what's in the news.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "triage_inbox",
        "description": "Run AI triage on the user's inbox — prioritise and suggest action per unread email. Use when they ask 'what's in my inbox' or 'triage my emails'.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "read_latest_emails",
        "description": "Fetch the user's most recent emails and read them back IN CHAT — sender, subject, and a short preview each. Use when the user asks to get/check/read their last email, latest email, newest emails, or what just arrived (and they want the content here, not just to open the inbox).",
        "parameters": {"type": "object", "properties": {
            "count": {"type": "integer", "description": "How many recent emails to fetch (default 3, max 10)."}}},
    },
    {
        "name": "give_olwen_the_wheel",
        "description": "Hand the user's Mac to Olwen for autonomous control. Olwen will see the screen, decide what to click/type, take a screenshot, look at the result, decide the next step, and repeat until the goal is reached. Use this when the user wants Olwen to actually FINISH a multi-step task on the screen — sending a real WhatsApp/Telegram message to a contact, filling out a form, navigating an app, anything where the one-shot tools above can't solve it. Requires a Claude API key.",
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "Plain-English goal Olwen should achieve, e.g., 'Send a WhatsApp message to Mohamed Elwan saying hello' or 'Find the cheapest flight to Cairo on Skyscanner'."},
            },
            "required": ["goal"],
        },
    },
    {
        "name": "find_contact",
        "description": "Search the user's macOS Contacts (address book) for someone by name and return their phone numbers. ALWAYS call this BEFORE send_message when the user names a person ('Mohamed', 'my mom', 'Ahmed'). Skip it only when the user already gave a phone number or a @username.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Person's name as the user said it (partial OK — fuzzy matched)."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "send_message",
        "description": "Compose a WhatsApp or Telegram message on this Mac. Opens the chat with the text pre-filled — the user hits Send. Use when the user asks 'send a WhatsApp/Telegram to <someone> saying <text>' or 'message <name> on whatsapp/telegram'.",
        "parameters": {
            "type": "object",
            "properties": {
                "app": {"type": "string", "description": "Which messenger: 'whatsapp' or 'telegram'."},
                "to": {"type": "string", "description": "Recipient phone number (international format, no +, e.g. 966555123456) for WhatsApp, or @username for Telegram. Use 'self' to message yourself."},
                "text": {"type": "string", "description": "The message body."},
            },
            "required": ["app", "text"],
        },
    },
    {
        "name": "open_mac_app",
        "description": "Open a native macOS application by name (Chrome, Safari, Spotify, VS Code, Slack, Notes, Mail, Calendar, etc.). Use when the user says 'open <app>', 'launch <app>', or 'start <app>'. The app runs on the user's own machine via `open -a`.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Application name as it appears in /Applications (e.g., 'Google Chrome', 'Safari', 'Visual Studio Code')."},
                "url": {"type": "string", "description": "Optional URL or file to open with the app."},
            },
            "required": ["name"],
        },
    },
]


def build_tools(installed_keys: list[str]) -> list[dict]:
    decls: list[dict] = []
    if "tasks" in installed_keys:
        decls.extend(_TASK_DECLS)
    has_search = "brave-search" in installed_keys or "exa" in installed_keys
    if has_search and settings.brave_api_key:
        decls.append(_SEARCH_DECL)
    # UI tools are always available — Olwen should always be able to open himself
    decls.extend(_UI_DECLS)
    # Memory tools are always available — Olwen should always be able to remember/recall.
    decls.extend(_MEMORY_DECLS)
    return [{"function_declarations": decls}] if decls else []


# ---- tool execution ----
async def _first_list(user_id, session: AsyncSession) -> TaskList:
    tl = await session.scalar(
        select(TaskList).where(TaskList.user_id == user_id).order_by(TaskList.created_at).limit(1)
    )
    if tl is None:
        tl = TaskList(user_id=user_id, name="Tasks")
        session.add(tl); await session.commit(); await session.refresh(tl)
    return tl


async def _brave_search(query: str) -> dict:
    if not settings.brave_api_key:
        return {"error": "Web search is installed but no Brave API key is configured on the server."}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": settings.brave_api_key, "Accept": "application/json"},
                params={"q": query, "count": 5},
            )
            r.raise_for_status()
            data = r.json()
            results = (data.get("web") or {}).get("results") or []
            return {
                "query": query,
                "results": [
                    {"title": x.get("title", ""), "url": x.get("url", ""),
                     "snippet": (x.get("description") or "")[:280]}
                    for x in results[:5]
                ],
            }
    except Exception as exc:
        return {"error": f"Search failed: {exc}"}


def _bridge_conn() -> tuple[str, str]:
    """(base_url, bearer_token) for the local Olwen bridge."""
    base = settings.bridge_url.rstrip("/")
    token = pathlib.Path(os.path.expanduser(settings.bridge_token_path)).read_text().strip()
    return base, token


async def _wa_send_via_ax(to: str, text: str, self_name: str = "") -> dict:
    """Send a WhatsApp message DETERMINISTICALLY via the bridge's Accessibility
    endpoints — find the real chat + message box by identity, type with the real
    keyboard, verify it landed. No AppleScript, no vision model, no tokens.
    """
    is_self = (not to) or to.strip().lower() in ("self", "me", "you", "(you)", "myself")
    label = "you" if is_self else to
    try:
        base, token = _bridge_conn()
    except Exception as exc:  # noqa: BLE001 — token missing / bridge never installed
        return {"ok": False, "say": f"The Olwen bridge isn't set up ({exc})."}

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(base_url=base, headers=headers, timeout=15.0) as c:
        async def act(**sel) -> bool:
            r = await c.post("/ax/act", json={"app": "WhatsApp", **sel})
            return r.status_code == 200

        async def find(**sel) -> list:
            r = await c.post("/ax/find", json={"app": "WhatsApp", **sel})
            return r.json().get("matches", []) if r.status_code == 200 else []

        async def type_text(t: str) -> None:
            await c.post("/key/type", json={"text": t})

        async def press(*keys: str) -> None:
            await c.post("/key/press", json={"keys": list(keys)})

        # 0) bridge reachable?
        try:
            if (await c.get("/health")).status_code != 200:
                return {"ok": False, "say": "The Olwen bridge isn't responding."}
        except Exception:  # noqa: BLE001
            return {"ok": False, "say": "The Olwen bridge isn't running — open Olwen.app."}

        # Remember where the user was (Olwen's browser/app) so we can hand focus
        # back when we're done — they should see Olwen, not be stranded in WhatsApp.
        prev_front = ""
        try:
            fr = await c.get("/ax/frontmost")
            if fr.status_code == 200:
                prev_front = fr.json().get("bundle") or fr.json().get("name") or ""
        except Exception:  # noqa: BLE001
            pass

        async def _return_to_olwen() -> None:
            if prev_front:
                try:
                    await c.post("/ax/activate", json={"app": prev_front})
                except Exception:  # noqa: BLE001
                    pass

        async def _send() -> dict:
            # 1) Bring WhatsApp to the front (Chats tab press also activates it).
            if not await act(desc="Chats", action="press", activate=True):
                return {"ok": False, "say": "Couldn't reach WhatsApp — is it installed and running?"}
            await asyncio.sleep(0.6)

            # 2) open the target chat
            if is_self:
                # "New Chat → Message yourself" reaches the self-chat reliably —
                # the main chat list is virtualized so the pinned self-chat can
                # scroll out of the tree, but the New-Chat picker always lists it.
                await act(desc="New Chat", action="press")
                await asyncio.sleep(1.0)
                opened = await act(role="AXStaticText", value_contains="Message yourself", action="press")
            else:
                # Search for the contact by name, then open the matching row.
                await act(role="AXTextField", placeholder_contains="search", action="focus")
                await press("command", "a"); await press("delete")
                await type_text(to)
                await asyncio.sleep(1.4)
                opened = await act(role="AXButton", desc_contains=to, action="press")
            if not opened:
                return {"ok": False, "say": f"I couldn't find your WhatsApp chat with {label}."}
            await asyncio.sleep(1.0)

            # 3) focus the composer, type, send
            if not await act(role="AXTextArea", desc="Compose message", action="focus"):
                return {"ok": False, "say": "Opened the chat but couldn't find the message box."}
            await asyncio.sleep(0.3)
            await type_text(text)
            await asyncio.sleep(0.3)
            await press("enter")
            await asyncio.sleep(1.1)

            # 4) verify the message is now in the conversation
            if await find(value_contains=text[:30]):
                return {"ok": True, "say": f"Sent to {label} on WhatsApp — confirmed it's in the chat."}
            return {"ok": True, "verified": False,
                    "say": f"I sent it to {label}, but couldn't confirm it landed — mind a glance?"}

        result = await _send()
        await _return_to_olwen()   # hand focus back so the user sees Olwen's reply
        return result


async def _wa_read_self_last() -> str:
    """Read the latest message in your WhatsApp self-chat that ISN'T one of Olwen's
    own automated pings (those start with ⚠/✅) — i.e. your reply. Best-effort."""
    import re as _re
    try:
        base, token = _bridge_conn()
    except Exception:  # noqa: BLE001
        return ""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(base_url=base, headers=headers, timeout=15.0) as c:
        async def act(**sel) -> bool:
            r = await c.post("/ax/act", json={"app": "WhatsApp", **sel})
            return r.status_code == 200
        try:
            if not await act(desc="Chats", action="press", activate=True):
                return ""
            await asyncio.sleep(0.5)
            await act(desc="New Chat", action="press")
            await asyncio.sleep(0.9)
            if not await act(role="AXStaticText", value_contains="Message yourself", action="press"):
                return ""
            await asyncio.sleep(1.0)
            r = await c.post("/ax/find", json={"app": "WhatsApp", "role": "AXStaticText", "limit": 250})
            vals = [m.get("value", "") for m in r.json().get("matches", [])] if r.status_code == 200 else []
        except Exception:  # noqa: BLE001
            return ""
    msgs: list[str] = []
    for v in vals:
        m = _re.match(r"Your message, (.+?), \d{1,2}:\d{2}", v)
        if m:
            msgs.append(m.group(1).strip())
    # the user's reply = the last bubble that isn't one of Olwen's ⚠/✅ pings
    for text in reversed(msgs):
        if text and text[0] not in ("⚠", "✅", "🤖"):
            return text
    return ""


async def _exec_tool(name: str, args: dict, user: User, session: AsyncSession) -> dict:
    if name == "list_tasks":
        rows = await session.execute(
            select(Task, TaskList.name).join(TaskList, Task.list_id == TaskList.id)
            .where(Task.user_id == user.id, Task.done.is_(False)).order_by(Task.created_at)
        )
        return {"tasks": [{"text": t.text, "list": n, "priority": t.priority} for t, n in rows.all()]}

    if name == "add_task":
        text = (args.get("text") or "").strip()
        if not text:
            return {"error": "no text"}
        tl = await _first_list(user.id, session)
        session.add(Task(user_id=user.id, list_id=tl.id, text=text, priority="med"))
        await session.commit()
        return {"status": "created", "task": text, "list": tl.name}

    if name == "complete_task":
        words = (args.get("text") or "").strip()
        task = await session.scalar(
            select(Task).where(
                Task.user_id == user.id, Task.done.is_(False), Task.text.ilike(f"%{words}%")
            ).limit(1)
        )
        if task is None:
            return {"status": "not_found", "query": words}
        task.done = True; await session.commit()
        return {"status": "completed", "task": task.text}

    if name == "web_search":
        return await _brave_search((args.get("query") or "").strip())

    # ---- long-term memory ----
    if name == "remember":
        from app.services.memory import add_memory, gemini_key_for
        m = await add_memory(
            user_id=user.id, session=session, content=args.get("content", ""),
            mem_type=args.get("type", "semantic"), subject=args.get("subject"),
            importance=int(args.get("importance", 7) or 7),
            source="user_explicit", gemini_key=gemini_key_for(user),
        )
        return {"ok": bool(m), "saved": m.content if m else None,
                "say": "Got it — I'll remember that."}

    if name == "recall_memory":
        from app.services.memory import gemini_key_for, recall
        rows = await recall(session, user.id, args.get("query", ""), gemini_key_for(user),
                            include_archived=True, limit=8)
        return {"matches": [
            {"content": r.content, "subject": r.subject, "type": r.mem_type,
             "archived": r.superseded_by is not None}
            for r in rows
        ]}

    # ---- UI tools — return structured `ui_action` payloads the frontend dispatches ----
    if name == "open_terminal":
        cwd = (args.get("cwd") or "").strip() or None
        cmd = (args.get("command") or "").strip() or None
        return {"ui_action": "open_terminal", "cwd": cwd, "command": cmd,
                "ok": True, "say": "Opening terminal now."}

    if name == "open_dev_mode":
        return {"ui_action": "open_dev_mode", "ok": True,
                "say": "Entering dev mode. Pick a project to start."}

    if name == "queue_dev_job":
        import asyncio as _aio
        from pathlib import Path as _P
        from app.api.routes.devmode import _scan_local
        from app.models.dev_job import DevJob
        from app.services.job_runner import run_job
        goal = (args.get("goal") or "").strip()
        if not goal:
            return {"error": "missing goal"}
        rows = await _aio.to_thread(_scan_local, _P.home())
        if not rows:
            return {"error": "No local git projects found."}
        hint = (args.get("project") or "").strip().lower()
        target = None
        if hint:
            for r in rows:
                if hint in r["name"].lower() or hint in r["rel"].lower():
                    target = r; break
        if target is None:
            target = rows[0]
        job = DevJob(user_id=user.id, project_path=target["path"],
                     project_name=target["name"], goal=goal, notify=True)
        session.add(job)
        await session.commit()
        await session.refresh(job)
        _aio.create_task(run_job(job.id, user.display_name or ""))
        return {"ok": True, "say": (f"Started a job on {target['name']}: {goal}. "
                                    "I'll open a PR and ping you when it's done.")}

    if name == "open_dev_studio":
        import asyncio as _aio
        from pathlib import Path as _P
        from app.api.routes.devmode import _scan_local
        rows = await _aio.to_thread(_scan_local, _P.home())
        if not rows:
            return {"error": "No local git projects found in your usual dev folders."}
        hints = [h.strip().lower() for h in (args.get("projects") or []) if h and h.strip()]
        chosen: list[dict] = []
        seen: set[str] = set()
        # First, honor any named hints (in order).
        for hint in hints:
            for r in rows:
                if r["path"] in seen:
                    continue
                if hint in r["name"].lower() or hint in r["rel"].lower():
                    chosen.append(r); seen.add(r["path"]); break
        # Fill the rest with the most recently modified projects.
        for r in rows:
            if len(chosen) >= 2:
                break
            if r["path"] not in seen:
                chosen.append(r); seen.add(r["path"])
        projects = [{"name": r["name"], "path": r["path"],
                     "autoStart": "claude --dangerously-skip-permissions"} for r in chosen[:2]]
        names = " + ".join(p["name"] for p in projects)
        return {
            "ui_action": "open_dev_studio",
            "projects": projects,
            "ok": True,
            "say": f"Opening Dev Studio — {names}. Two terminals, live tasks & pushes.",
        }

    if name == "list_projects":
        import asyncio as _aio
        from pathlib import Path as _P
        from app.api.routes.devmode import _scan_local
        rows = await _aio.to_thread(_scan_local, _P.home())
        return {"projects": [{"name": r["name"], "rel": r["rel"]} for r in rows[:20]]}

    if name == "open_project":
        import asyncio as _aio
        import shutil as _sh
        import subprocess as _sub
        import sys as _sys
        from pathlib import Path as _P
        from app.api.routes.devmode import _scan_local
        rows = await _aio.to_thread(_scan_local, _P.home())
        if not rows:
            return {"error": "No local git projects found in your usual dev folders."}
        match = (args.get("match") or "").strip().lower()
        target = None
        if match:
            for r in rows:
                if match in r["name"].lower() or match in r["rel"].lower():
                    target = r; break
        if target is None:
            target = rows[0]                                        # newest by mtime
        with_claude = args.get("with_claude", True)
        command = "claude --dangerously-skip-permissions" if with_claude else None
        # Also open the folder in Finder (macOS) / xdg-open (Linux) — same as the
        # DevMode click does. Non-fatal if the platform doesn't support it.
        try:
            if _sys.platform == "darwin":
                opener = "/usr/bin/open"
            elif _sys.platform.startswith("linux"):
                opener = _sh.which("xdg-open") or ""
            else:
                opener = ""
            if opener:
                _sub.Popen([opener, target["path"]],
                           stdout=_sub.DEVNULL, stderr=_sub.DEVNULL, start_new_session=True)
        except Exception:
            pass
        return {
            "ui_action": "open_terminal",
            "cwd": target["path"],
            "command": command,
            "ok": True,
            "project": target["name"],
            "path": target["path"],
            "say": (f"Opening {target['name']} with Claude Code (dangerous mode)."
                    if with_claude else f"Opening {target['name']}."),
        }

    if name == "open_settings":
        section = (args.get("section") or "connections").strip()
        return {"ui_action": "open_settings", "section": section, "ok": True,
                "say": f"Opening Settings → {section}."}

    if name == "open_compose_email":
        return {"ui_action": "open_compose_email", "ok": True,
                "say": "Opening the email composer."}

    if name == "run_morning_brief":
        return {"ui_action": "run_morning_brief", "ok": True,
                "say": "Pulling together your brief."}

    if name == "read_news":
        return {"ui_action": "read_news", "ok": True,
                "say": "Picking the top stories now."}

    if name == "triage_inbox":
        return {"ui_action": "triage_inbox", "ok": True,
                "say": "Triaging your inbox."}

    if name == "read_latest_emails":
        from app.api.routes.email import _fetch_for_account, _first_account
        acc = await _first_account(user.id, session)
        if acc is None:
            return {"error": "No email account is connected. Connect one in Settings → Email."}
        n = max(1, min(int(args.get("count", 3) or 3), 10))
        try:
            rows = await _fetch_for_account(acc, session, n)
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Couldn't reach the mailbox: {str(exc)[:160]}"}
        emails = [{
            "from": (r.get("sender") or "").split("<")[0].strip().strip('"') or r.get("sender", ""),
            "subject": r.get("subject") or "(no subject)",
            "preview": (r.get("snippet") or "")[:240],
            "unread": r.get("unread", False),
            "date": r.get("date", ""),
        } for r in rows[:n]]
        return {"emails": emails, "count": len(emails),
                "say": "Reading your latest emails." if emails else "Your inbox looks empty."}

    if name == "give_olwen_the_wheel":
        goal = (args.get("goal") or "").strip()
        if not goal:
            return {"error": "missing goal"}
        return {
            "ui_action": "open_computer_use",
            "instruction": goal,
            "auto_start": True,
            "say": f"Taking the wheel — {goal}. STOP button is at the top if you need to.",
        }

    if name == "find_contact":
        import subprocess
        q = (args.get("name") or "").strip()
        if not q:
            return {"error": "missing name"}
        script = f'''
        tell application "Contacts"
            set out to ""
            set matches to (every person whose name contains "{q}")
            repeat with p in matches
                set pn to (name of p)
                repeat with ph in (phones of p)
                    set out to out & pn & "|" & (value of ph) & linefeed
                end repeat
            end repeat
            return out
        end tell
        '''
        try:
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        except Exception as exc:  # noqa: BLE001
            return {"error": f"contacts lookup failed: {exc}"}
        lines = [l for l in (res.stdout or "").strip().splitlines() if "|" in l]
        contacts = [{"name": l.split("|", 1)[0].strip(), "phone": l.split("|", 1)[1].strip()} for l in lines]
        if not contacts:
            hint = " (macOS may need Contacts permission — System Settings → Privacy → Contacts)" if "1743" in (res.stderr or "") else ""
            return {"ok": True, "matches": [], "say": f"No contact named '{q}' found.{hint}"}
        return {"ok": True, "matches": contacts[:8], "say": f"Found {len(contacts)} match{'es' if len(contacts) > 1 else ''} for {q}."}

    if name == "send_message":
        import subprocess, urllib.parse
        app_kind = (args.get("app") or "").strip().lower()
        to = (args.get("to") or "").strip()
        text = (args.get("text") or "").strip()
        if not text:
            return {"error": "missing message text"}
        if app_kind in ("whatsapp", "wa"):
            # Deterministic send via the bridge's Accessibility endpoints: find
            # the real chat + message box by identity and type with the real
            # keyboard, then verify. No AppleScript, no vision model, no tokens.
            return await _wa_send_via_ax(to, text, self_name=user.display_name or "")
        if app_kind in ("telegram", "tg"):
            # Telegram deep-link: tg://msg?text=<encoded>&to=<username>
            user = to.lstrip("@") if to and to.lower() != "self" else ""
            url = f"tg://msg?text={urllib.parse.quote(text)}"
            if user:
                url = f"tg://resolve?domain={user}"  # open chat first
                subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # Then prep the message
                url2 = f"tg://msg?text={urllib.parse.quote(text)}"
                subprocess.Popen(["open", url2], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"ok": True, "say": "Opened Telegram with your message ready. Hit Send when you're happy with it."}
        return {"error": f"unsupported app '{app_kind}' — try 'whatsapp' or 'telegram'"}

    if name == "open_mac_app":
        # Fuzzy-find an app on the user's Mac and open it.
        import os, shutil, subprocess
        from difflib import get_close_matches

        wanted = (args.get("name") or "").strip()
        url = (args.get("url") or "").strip()
        if not wanted:
            return {"error": "missing app name"}

        # Build the catalog of installed apps from /Applications + ~/Applications
        catalog: dict[str, str] = {}
        for base in ["/Applications", "/System/Applications", os.path.expanduser("~/Applications")]:
            if not os.path.isdir(base):
                continue
            try:
                for entry in os.listdir(base):
                    if entry.endswith(".app"):
                        full = os.path.join(base, entry)
                        nm = entry[:-4]
                        catalog[nm.lower()] = nm  # key lowercase, value real name
            except PermissionError:
                continue

        # Aliases
        ALIASES = {
            "chrome": "Google Chrome", "vscode": "Visual Studio Code",
            "vs code": "Visual Studio Code", "code": "Visual Studio Code",
            "xcode": "Xcode", "iterm": "iTerm", "iterm2": "iTerm",
            "whatsapp": "WhatsApp", "ig": "Instagram", "x": "X",
            "twitter": "X", "vlc": "VLC", "ps": "Photoshop",
        }
        key = ALIASES.get(wanted.lower(), wanted).lower()

        # Exact match? close match? substring match?
        resolved = None
        if key in catalog:
            resolved = catalog[key]
        else:
            matches = get_close_matches(key, catalog.keys(), n=1, cutoff=0.6)
            if matches:
                resolved = catalog[matches[0]]
            else:
                # substring fallback (e.g. "chrome" → "Google Chrome")
                for k, v in catalog.items():
                    if key in k:
                        resolved = v; break

        if not resolved:
            installed = sorted(catalog.values())
            return {
                "error": f"'{wanted}' is not installed on this Mac",
                "say": f"I don't see {wanted} installed. Want me to open a different app?",
                "available_count": len(installed),
            }

        if not shutil.which("open"):
            return {"error": "macOS 'open' command not available"}
        cmd = ["open", "-a", resolved]
        if url:
            cmd.append(url)
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:  # noqa: BLE001
            return {"error": f"could not open {resolved}: {exc}"}
        return {"ok": True, "opened": resolved, "say": f"Opening {resolved}."}

    return {"error": f"unknown tool {name}"}


# ---- the loop ----
async def run_agent(
    message: str, history: list[dict], api_key: str, model: str, system: str,
    tools: list[dict], user: User, session: AsyncSession,
) -> dict:
    """Run a Gemini function-calling loop with the given tools.

    Returns: { "text": <final reply>, "ui_actions": [<dicts the FE dispatches>] }
    """
    contents: list[dict] = []
    for m in history:
        role = "model" if m.get("role") == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    # Make the model actually USE its tools instead of claiming it can't.
    tool_directive = (
        "\n\nYou have real tools that act on the user's Mac: open apps "
        "(open_mac_app), send WhatsApp/Telegram (send_message, after "
        "find_contact), control the screen end-to-end (give_olwen_the_wheel), "
        "manage tasks, search the web, and open your own surfaces. When the "
        "user asks you to do any of these, CALL THE TOOL — never reply that you "
        "can't. If a name is given, call find_contact first to get the number. "
        "If a request needs several screen steps, use give_olwen_the_wheel."
    )
    system = system + tool_directive

    ui_actions: list[dict] = []
    url = f"{GEMINI_BASE}/models/{model}:generateContent"
    async with httpx.AsyncClient(timeout=60) as client:
        for _ in range(6):
            body: dict = {"system_instruction": {"parts": [{"text": system}]}, "contents": contents}
            if tools:
                body["tools"] = tools
            # Retry transient Gemini failures (503 overloaded, 429 rate-limit)
            # with exponential backoff so the user doesn't see Google's hiccups.
            last_exc: Exception | None = None
            for attempt in range(4):
                try:
                    resp = await client.post(url, headers={"x-goog-api-key": api_key}, json=body)
                    if resp.status_code in (429, 500, 502, 503, 504):
                        last_exc = httpx.HTTPStatusError(f"transient {resp.status_code}", request=resp.request, response=resp)
                        await asyncio.sleep(1.5 * (2 ** attempt))  # 1.5, 3, 6, 12s
                        continue
                    resp.raise_for_status()
                    last_exc = None
                    break
                except httpx.HTTPError as e:
                    last_exc = e
                    await asyncio.sleep(1.5 * (2 ** attempt))
            if last_exc:
                raise last_exc
            data = resp.json()
            content = (data.get("candidates") or [{}])[0].get("content", {})
            parts = content.get("parts", [])
            calls = [p["functionCall"] for p in parts if "functionCall" in p]
            if not calls:
                text = " ".join(p.get("text", "") for p in parts).strip() or "Done."
                return {"text": text, "ui_actions": ui_actions}
            contents.append(content)
            responses = []
            for fc in calls:
                result = await _exec_tool(fc.get("name", ""), fc.get("args", {}), user, session)
                # Pull out UI actions so the frontend can act on them directly
                if isinstance(result, dict) and "ui_action" in result:
                    ui_actions.append({k: v for k, v in result.items() if k != "say"})
                responses.append({"functionResponse": {"name": fc.get("name", ""), "response": result}})
            contents.append({"role": "user", "parts": responses})
    return {"text": "I started on that but couldn't fully finish — try rephrasing?",
            "ui_actions": ui_actions}


async def stream_text(text: str) -> AsyncIterator[str]:
    """Chunk a finished reply into word deltas so the entity still animates."""
    import asyncio
    for word in text.split(" "):
        await asyncio.sleep(0.02)
        yield word + " "
