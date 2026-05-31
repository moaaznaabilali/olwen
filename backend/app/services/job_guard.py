#!/usr/bin/env python
"""PreToolUse guard for unattended Olwen jobs.

Claude Code runs this before every Bash command. It scans the FULL command (so
chained `... && git push origin main` is caught too) and BLOCKS anything
irreversible, out-of-scope, or that should need a human: pushing to a remote,
deploying/publishing, destructive deletes, remote-machine access, DB drops, sudo.

Reads the tool call as JSON on stdin. Exit 0 = allow; exit 2 + stderr = block
(Claude Code surfaces the reason and won't run it).
"""
import json
import re
import sys

# (pattern, human reason) — matched case-insensitively ANYWHERE in the command.
DANGER = [
    (r"\bgit\s+push\b", "push to a remote — Olwen handles pushing to a safe branch and opening a PR"),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard (throws away work)"),
    (r"\bgit\s+clean\s+-\w*f", "git clean -f (deletes files)"),
    (r"\bgit\s+branch\s+-D\b", "force-deleting a branch"),
    (r"\brm\s+-\w*r\w*f|\brm\s+-\w*f\w*r", "a recursive force delete (rm -rf)"),
    (r"\bsudo\b", "sudo (elevated privileges)"),
    (r"\b(npm|pnpm|yarn)\s+publish\b", "publishing a package"),
    (r"\bgh\s+release\b", "creating a GitHub release"),
    (r"\b(kubectl|terraform|helm|ansible|pulumi|serverless)\b", "an infrastructure/deploy command"),
    (r"\b(ssh|scp|rsync)\b", "accessing a remote machine"),
    (r"\bdeploy(\.sh)?\b", "a deploy command"),
    (r"\bdropdb\b|\bDROP\s+(TABLE|DATABASE)\b|\bTRUNCATE\b|\bdelete\s+from\b", "a destructive database command"),
    (r"\bmkfs\b|\bdd\s+if=", "a disk-wipe command"),
    (r":\s*\(\s*\)\s*\{", "a fork bomb"),
    (r"\bcurl\b[^|]*\|\s*(sh|bash)\b", "piping a remote script into a shell"),
]
_COMPILED = [(re.compile(p, re.I), why) for p, why in DANGER]


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0  # can't parse → don't block (fail open on parse, the patterns are the safety net)
    cmd = ""
    ti = data.get("tool_input") or {}
    if isinstance(ti, dict):
        cmd = str(ti.get("command") or ti.get("cmd") or "")
    if not cmd:
        return 0
    for rx, why in _COMPILED:
        if rx.search(cmd):
            sys.stderr.write(
                f"BLOCKED by Olwen's unattended guardrails: {why}. "
                f"This is not allowed in an autonomous run — make the code changes only; "
                f"Olwen will open a PR. If this action is truly needed, stop and say so so the human can decide."
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
