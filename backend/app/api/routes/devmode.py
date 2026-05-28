"""Dev Mode — Olwen's focus environment for coders.

Lists the user's projects (GitHub repos + local git directories) so they can
pick a project and have Olwen open a terminal pre-cwd'd to it.
"""
import asyncio
import datetime as dt
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.core.security import decrypt_secret
from app.models.github_account import GithubAccount
from app.services import github_oauth

router = APIRouter()

# Common dev folders to scan for git repos
DEV_ROOTS = [
    "Documents/projects", "Documents/Projects", "Documents/code", "Documents/Code",
    "code", "Code", "Workspace", "workspace", "dev", "Dev", "Developer",
    "Projects", "projects", "Sites", "src",
]
MAX_DEPTH = 3
MAX_DIRS = 60


def _is_git_repo(p: Path) -> bool:
    return (p / ".git").is_dir() or (p / ".git").is_file()


def _scan_local(home: Path) -> list[dict[str, Any]]:
    """Walk known dev roots a few levels deep and surface every git repo.

    Dedupes by `realpath` so case-different roots on macOS (Documents/projects
    vs Documents/Projects, which resolve to the same inode) don't show twice.
    """
    found: dict[tuple[int, int], dict[str, Any]] = {}    # key = (st_dev, st_ino)
    for root_name in DEV_ROOTS:
        root = home / root_name
        if not root.is_dir():
            continue
        try:
            stack: list[tuple[Path, int]] = [(root, 0)]
            while stack and len(found) < MAX_DIRS:
                cur, depth = stack.pop(0)
                if _is_git_repo(cur):
                    try:
                        st = os.stat(cur)
                        ino_key = (st.st_dev, st.st_ino)
                    except OSError:
                        continue
                    if ino_key not in found:
                        path_str = str(cur)
                        try:
                            rel = str(cur.relative_to(home))
                        except ValueError:
                            rel = path_str
                        found[ino_key] = {
                            "key": path_str,
                            "name": cur.name,
                            "path": path_str,
                            "rel": rel,
                            "modified": dt.datetime.fromtimestamp(st.st_mtime, dt.timezone.utc).isoformat() if st.st_mtime else None,
                        }
                    continue  # don't descend INTO a git repo
                if depth >= MAX_DEPTH:
                    continue
                try:
                    for child in cur.iterdir():
                        if child.is_dir() and not child.name.startswith(".") and child.name != "node_modules":
                            stack.append((child, depth + 1))
                except (PermissionError, OSError):
                    continue
        except Exception:  # noqa: BLE001
            continue
    out = list(found.values())
    out.sort(key=lambda x: x.get("modified") or "", reverse=True)
    return out[:MAX_DIRS]


async def _scan_local_async(home: Path) -> list[dict]:
    return await asyncio.to_thread(_scan_local, home)


async def _github_repos(user_id, session: SessionDep) -> list[dict[str, Any]]:
    """Top 30 repos for the user's connected GitHub account (newest pushed first)."""
    acc = await session.scalar(select(GithubAccount).where(GithubAccount.user_id == user_id))
    if acc is None:
        return []
    token = decrypt_secret(acc.access_token_enc)
    import httpx
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            params={"sort": "pushed", "per_page": 30, "affiliation": "owner,collaborator"},
        )
        if r.status_code != 200:
            return []
        rows = r.json()
    return [{
        "key": f"gh:{r['id']}",
        "name": r["name"],
        "full_name": r["full_name"],
        "description": (r.get("description") or "")[:160],
        "language": r.get("language") or "",
        "stars": r.get("stargazers_count", 0),
        "private": r.get("private", False),
        "pushed_at": r.get("pushed_at") or "",
        "url": r.get("html_url") or "",
        "clone_url": r.get("clone_url") or "",
        "ssh_url": r.get("ssh_url") or "",
    } for r in rows]


@router.post("/open-in-finder")
async def open_in_finder(payload: dict, user: CurrentUser) -> dict:
    """Open the given path in the host's native file browser.

    Runs `/usr/bin/open <path>` on macOS (or `xdg-open` on Linux). The path
    must exist as a directory the backend can see. Returns ok=False if it
    can't (we never raise so a missing path doesn't fail the project launch).
    """
    import shutil
    import subprocess
    import sys

    path = (payload.get("path") or "").strip()
    if not path or not os.path.isdir(path):
        return {"ok": False, "reason": "path missing"}

    if sys.platform == "darwin":
        opener = "/usr/bin/open"
    elif sys.platform.startswith("linux"):
        opener = shutil.which("xdg-open") or ""
    else:
        opener = ""
    if not opener:
        return {"ok": False, "reason": "no opener on this platform"}

    try:
        subprocess.Popen(
            [opener, path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": str(exc)[:120]}


@router.get("/projects")
async def projects(user: CurrentUser, session: SessionDep) -> dict:
    """Aggregate local git repos + GitHub repos for the project picker."""
    home = Path.home()
    local, github = await asyncio.gather(
        _scan_local_async(home),
        _github_repos(user.id, session),
    )
    return {
        "local": local,
        "github": github,
        "home": str(home),
    }
