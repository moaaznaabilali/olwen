"""Project intelligence — read a local project's git state + PRD/phases so Olwen
can tell you where Claude Code stopped and where to resume.

Read-only. Restricted to git repos under the user's home directory.
"""
import os
import re
import subprocess
from pathlib import Path

# Where a project's plan tends to live, in priority order.
PRD_NAMES = [
    "PRD.md", "prd.md", "docs/PRD.md", "docs/prd.md",
    "ROADMAP.md", "roadmap.md", "docs/ROADMAP.md",
    "PLAN.md", "plan.md", "TODO.md", "todo.md",
]
_PHASE_HEAD = re.compile(r"^#{1,4}\s*((?:phase|milestone|stage|step|sprint)\b[^\n]*)", re.I)
_CHECKBOX = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*(.+)$")


def _git(path: Path, *args: str, timeout: int = 6) -> str:
    try:
        r = subprocess.run(["git", "-C", str(path), *args],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def _safe(path_str: str) -> Path | None:
    """Resolve a user-supplied path, only allowing git repos under $HOME."""
    try:
        p = Path(os.path.expanduser(path_str)).resolve()
    except Exception:  # noqa: BLE001
        return None
    home = Path.home().resolve()
    if p != home and home not in p.parents:
        return None
    if not (p / ".git").exists():
        return None
    return p


def _find_prd(path: Path) -> tuple[str, str]:
    for name in PRD_NAMES:
        f = path / name
        if f.is_file():
            try:
                return name, f.read_text(errors="ignore")[:20000]
            except Exception:  # noqa: BLE001
                pass
    # Fall back to a Roadmap/Phases section inside the README.
    for rd in ("README.md", "readme.md"):
        f = path / rd
        if not f.is_file():
            continue
        try:
            txt = f.read_text(errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        m = re.search(r"(^#{1,3}\s*(?:roadmap|phases|milestones|plan)[\s\S]+?)(?=^#{1,2}\s|\Z)",
                      txt, re.I | re.M)
        if m:
            return rd, m.group(1)[:20000]
    return "", ""


def _phases(prd: str) -> list[dict]:
    phases: list[dict] = []
    cur: dict | None = None
    for line in prd.splitlines():
        hm = _PHASE_HEAD.match(line.strip())
        if hm:
            cur = {"title": re.sub(r"^#+\s*", "", line.strip())[:90], "items": []}
            phases.append(cur)
            continue
        cm = _CHECKBOX.match(line)
        if cm:
            if cur is None:
                cur = {"title": "Tasks", "items": []}
                phases.append(cur)
            cur["items"].append({"text": cm.group(2).strip()[:120],
                                 "done": cm.group(1).lower() == "x"})
    for ph in phases:
        ph["done"] = sum(1 for i in ph["items"] if i["done"])
        ph["total"] = len(ph["items"])
    return [p for p in phases if p["items"]][:8]


def gather_intel(path_str: str) -> dict:
    p = _safe(path_str)
    if p is None:
        return {"ok": False, "reason": "not a readable git project under your home"}

    branch = _git(p, "rev-parse", "--abbrev-ref", "HEAD") or "—"
    log = _git(p, "log", "-6", "--pretty=%h\x01%s\x01%cr\x01%an")
    commits = []
    for line in log.splitlines():
        parts = line.split("\x01")
        if len(parts) == 4:
            commits.append({"hash": parts[0], "subject": parts[1],
                            "when": parts[2], "author": parts[3]})

    dirty_raw = _git(p, "status", "--porcelain")
    dirty = [ln[3:] for ln in dirty_raw.splitlines()][:14] if dirty_raw else []

    ahead = behind = 0
    ab = _git(p, "rev-list", "--left-right", "--count", "@{u}...HEAD")
    if ab and "\t" in ab:
        try:
            b, a = ab.split("\t")
            behind, ahead = int(b), int(a)
        except Exception:  # noqa: BLE001
            pass

    prd_name, prd = _find_prd(p)
    phases = _phases(prd) if prd else []

    stopped = ""
    if commits:
        stopped = f'Last commit: "{commits[0]["subject"]}" ({commits[0]["when"]}).'
    if dirty:
        stopped += f" {len(dirty)} uncommitted change(s) in progress."
    if ahead:
        stopped += f" {ahead} commit(s) not yet pushed."

    return {
        "ok": True,
        "name": p.name,
        "branch": branch,
        "commits": commits,
        "dirty": dirty,
        "ahead": ahead,
        "behind": behind,
        "prd_name": prd_name,
        "phases": phases,
        "stopped": stopped or "Fresh repo — no commits yet.",
    }
