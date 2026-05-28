"""Tool-using agent loop (Gemini).

Lets Olwen actually RUN skills via function-calling. Tools exposed to the model
are built dynamically from the user's installed skills (e.g. Tasks, Web Search).
Other providers/skills follow this same pattern.
"""
from collections.abc import AsyncIterator

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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

    # ---- UI tools — return structured `ui_action` payloads the frontend dispatches ----
    if name == "open_terminal":
        cwd = (args.get("cwd") or "").strip() or None
        cmd = (args.get("command") or "").strip() or None
        return {"ui_action": "open_terminal", "cwd": cwd, "command": cmd,
                "ok": True, "say": "Opening terminal now."}

    if name == "open_dev_mode":
        return {"ui_action": "open_dev_mode", "ok": True,
                "say": "Entering dev mode. Pick a project to start."}

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

    ui_actions: list[dict] = []
    url = f"{GEMINI_BASE}/models/{model}:generateContent"
    async with httpx.AsyncClient(timeout=60) as client:
        for _ in range(6):
            body: dict = {"system_instruction": {"parts": [{"text": system}]}, "contents": contents}
            if tools:
                body["tools"] = tools
            resp = await client.post(url, headers={"x-goog-api-key": api_key}, json=body)
            resp.raise_for_status()
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
