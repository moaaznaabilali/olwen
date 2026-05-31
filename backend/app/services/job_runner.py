"""Unattended job runner — Olwen runs Claude Code on a goal while you're away.

Server-side so it survives the browser closing. Works ONLY on a fresh branch and
opens a PR — nothing lands on main without you. Bounded parallelism. When Claude
Code needs a decision, the job goes 'needs_you', Olwen WhatsApps the question, and
your reply RESUMES the same Claude Code session. Coding is `claude -p` headless on
YOUR subscription; Olwen frames, manages, commits, and notifies.
"""
import asyncio
import json
import os
import re
import sys
import uuid

from app.core.database import SessionLocal
from app.models.dev_job import DevJob

# Bounded pool — a few jobs run at once; the rest wait as 'queued'.
_SEM = asyncio.Semaphore(3)

# Guardrails: a PreToolUse hook (sees the FULL command, catches chained ones) +
# disallowed-tool patterns as defense in depth. Blocks push/deploy/delete/etc.
_GUARD = os.path.join(os.path.dirname(__file__), "job_guard.py")
_GUARD_SETTINGS = json.dumps({
    "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": f"{sys.executable} {_GUARD}"}
    ]}]}
})
_DISALLOWED = [
    "Bash(git push:*)", "Bash(sudo:*)", "Bash(rm -rf:*)", "Bash(rm -fr:*)",
    "Bash(gh release:*)", "Bash(npm publish:*)", "Bash(pnpm publish:*)",
    "Bash(kubectl:*)", "Bash(terraform:*)", "Bash(ssh:*)", "Bash(scp:*)",
]

_ASK_HINT = re.compile(r"\b(which|should i|do you want|would you like|clarif|prefer|not sure|please specify|\?)", re.I)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "task"


async def _run(cwd: str, *args: str, timeout: float | None = None) -> tuple[int, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, cwd=cwd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
    except Exception as exc:  # noqa: BLE001
        return 127, f"could not start {args[0]}: {exc}"
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
        return 124, "(timed out)"
    return proc.returncode or 0, (out or b"").decode(errors="ignore")


async def _claude(cwd: str, *prompt_args: str) -> tuple[str, str]:
    """Run claude -p headless, return (result_text, session_id). stderr is kept
    SEPARATE so notices don't corrupt the JSON on stdout."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", *prompt_args,
            "--output-format", "json", "--dangerously-skip-permissions",
            "--settings", _GUARD_SETTINGS,
            "--disallowedTools", *_DISALLOWED,
            cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=1800)
        out = (out_b or b"").decode(errors="ignore").strip()
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
        return "(Claude Code timed out)", ""
    except Exception as exc:  # noqa: BLE001
        return f"(couldn't run Claude Code: {exc})", ""
    data: dict = {}
    try:
        data = json.loads(out)
    except Exception:  # noqa: BLE001
        m = re.search(r'\{"type":"result".*\}', out, re.S)
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception:  # noqa: BLE001
                data = {}
    return str(data.get("result") or out[-2000:])[:6000], str(data.get("session_id") or "")


async def _notify(self_name: str, text: str) -> None:
    try:
        from app.services.agent import _wa_send_via_ax
        await _wa_send_via_ax("me", text, self_name=self_name)
    except Exception:  # noqa: BLE001
        pass


async def _set(db, job: DevJob, **fields) -> None:
    for k, v in fields.items():
        setattr(job, k, v)
    await db.commit()


async def _finalize(db, job: DevJob, result: str, self_name: str, base_sha: str = "") -> None:
    """After Claude Code runs: commit + PR if it did work, else ask for help.
    Work = uncommitted changes OR new commits (Claude Code often commits itself)."""
    path = job.project_path
    _, dirty = await _run(path, "git", "status", "--porcelain", timeout=15)
    ahead = "0"
    if base_sha:
        _, ahead = await _run(path, "git", "rev-list", "--count", f"{base_sha}..HEAD", timeout=15)
    did_work = bool(dirty.strip()) or (ahead.strip() not in ("", "0"))
    if not did_work:
        # No changes at all — Claude Code likely needs a decision. Ask the human.
        q = result.strip().splitlines()[-1][:300] if result.strip() else "It made no changes — can you clarify the goal?"
        await _set(db, job, status="needs_you", question=q,
                   note="Waiting on your reply to continue.")
        if job.notify:
            await _notify(self_name, f"⚠ '{job.goal}'\nOlwen needs you: {q}\nReply here and I'll continue.")
        return
    await _run(path, "git", "add", "-A", timeout=20)
    await _run(path, "git", "commit", "-m", f"{job.goal}\n\n(autonomous run via Olwen)", timeout=30)
    pr_url = ""
    rc_push, _ = await _run(path, "git", "push", "-u", "origin", job.branch, timeout=60)
    if rc_push == 0:
        _, pr_out = await _run(path, "gh", "pr", "create", "--fill", "--head", job.branch, timeout=60)
        m = re.search(r"https?://\S+", pr_out)
        if m:
            pr_url = m.group(0)
    note = f"Committed to {job.branch}" + (f" · PR {pr_url}" if pr_url else " (no remote — local branch)")
    await _set(db, job, status="done", pr_url=pr_url, question="", note=note)
    if job.notify:
        tail = (result.strip().splitlines() or [""])[-1][:140]
        await _notify(self_name, f"✅ Done: '{job.goal}'\n{tail}\n{pr_url or note}")


async def run_job(job_id: uuid.UUID, self_name: str = "") -> None:
    async with SessionLocal() as db:
        job = await db.get(DevJob, job_id)
        if job is None:
            return
        goal = job.goal
        async with _SEM:                       # bounded parallelism (queues here)
            try:
                await _set(db, job, status="running")
                branch = f"olwen/{_slug(goal)}-{str(job.id)[:6]}"
                rc, out = await _run(job.project_path, "git", "checkout", "-B", branch, timeout=20)
                if rc != 0:
                    await _set(db, job, status="failed", note=f"git branch failed: {out[:200]}")
                    return
                await _set(db, job, branch=branch)
                _, base_sha = await _run(job.project_path, "git", "rev-parse", "HEAD", timeout=10)
                brief = (
                    f"{goal}\n\nWork fully autonomously: explore the project, make ALL the edits, "
                    f"and verify. Prefer sensible defaults over asking. Only if a decision truly "
                    f"can't be made safely, end your reply with a single clear question."
                )
                result, sid = await _claude(job.project_path, brief)
                await _set(db, job, output=result[-4000:], session_id=sid or None)
                await _finalize(db, job, result, self_name, base_sha.strip())
            except Exception as exc:  # noqa: BLE001
                await _set(db, job, status="failed", note=f"Run error: {exc}"[:400])
                if job.notify:
                    await _notify(self_name, f"⚠ '{goal}' failed: {exc}"[:180])


async def resume_job(job_id: uuid.UUID, answer: str, self_name: str = "") -> None:
    """Continue a 'needs_you' job with the user's reply (resumes the Claude session)."""
    async with SessionLocal() as db:
        job = await db.get(DevJob, job_id)
        if job is None or job.status not in ("needs_you", "failed"):
            return
        async with _SEM:
            try:
                await _set(db, job, status="running", question="")
                if job.branch:
                    await _run(job.project_path, "git", "checkout", job.branch, timeout=20)
                _, base_sha = await _run(job.project_path, "git", "rev-parse", "HEAD", timeout=10)
                follow = f"{answer}\n\nNow finish the task fully and autonomously."
                if job.session_id:
                    result, sid = await _claude(job.project_path, "--resume", job.session_id, follow)
                else:
                    result, sid = await _claude(job.project_path, f"{job.goal}\n\n{follow}")
                await _set(db, job, output=result[-4000:], session_id=sid or job.session_id)
                await _finalize(db, job, result, self_name, base_sha.strip())
            except Exception as exc:  # noqa: BLE001
                await _set(db, job, status="failed", note=f"Resume error: {exc}"[:400])


_reply_baseline: str | None = None


async def whatsapp_reply_poller() -> None:
    """While a job is 'needs_you', watch your WhatsApp self-chat for a reply and
    resume the job with it. Experimental — WhatsApp has no inbound API, so this
    polls (and briefly brings WhatsApp forward). Disabled when no job is waiting."""
    global _reply_baseline
    from sqlalchemy import select
    from app.models.user import User
    while True:
        await asyncio.sleep(45)
        try:
            async with SessionLocal() as db:
                jobs = (await db.execute(
                    select(DevJob).where(DevJob.status == "needs_you", DevJob.notify.is_(True))
                    .order_by(DevJob.created_at)
                )).scalars().all()
                if not jobs:
                    _reply_baseline = None
                    continue
                job = jobs[0]
                user = await db.get(User, job.user_id)
                name = (user.display_name if user else "") or ""
            from app.services.agent import _wa_read_self_last
            last = await _wa_read_self_last()
            if _reply_baseline is None:
                _reply_baseline = last or ""   # first look — baseline, don't act
                continue
            if last and last != _reply_baseline:
                _reply_baseline = last
                await resume_job(job.id, last, name)
        except Exception:  # noqa: BLE001
            pass


async def redispatch_queued() -> None:
    """On startup: re-pick jobs left queued/running (orphaned by a restart)."""
    from sqlalchemy import select
    from app.models.user import User
    async with SessionLocal() as db:
        rows = (await db.execute(select(DevJob).where(DevJob.status.in_(("queued", "running"))))).scalars().all()
        for job in rows:
            job.status = "queued"
            user = await db.get(User, job.user_id)
            name = (user.display_name if user else "") or ""
            asyncio.create_task(run_job(job.id, name))
        if rows:
            await db.commit()
