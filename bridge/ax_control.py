"""macOS Accessibility (AX) control — find and act on REAL UI elements.

Instead of guessing pixel coordinates from a screenshot, this reads an app's
accessibility tree (the same data screen-readers use) and targets widgets by
identity: "the chat row whose name is 'Me Zain'", "the field whose placeholder
is 'Search'". Deterministic, instant, and free — no model, no vision.

Requires Accessibility permission (AXIsProcessTrusted), the same grant pyautogui
needs to move the mouse. Imports are guarded so the bridge still boots (and the
mouse/keyboard endpoints keep working) even if PyObjC's AX framework is missing.
"""
from __future__ import annotations

import time

try:
    from ApplicationServices import (
        AXIsProcessTrusted,
        AXUIElementCopyAttributeValue,
        AXUIElementCreateApplication,
        AXUIElementPerformAction,
        AXUIElementSetAttributeValue,
    )
    from AppKit import NSWorkspace
    AX_AVAILABLE = True
    AX_IMPORT_ERROR = ""
except Exception as exc:  # noqa: BLE001 — pyobjc / framework not installed
    AX_AVAILABLE = False
    AX_IMPORT_ERROR = str(exc)

# Attributes we surface for every element. Bidi/format marks stripped for matching.
_NOISE = {"‎": "", "‏": "", " ": " ", "‪": "", "‬": ""}


def _norm(s) -> str:
    s = str(s) if s is not None else ""
    for bad, good in _NOISE.items():
        s = s.replace(bad, good)
    return s.strip()


def _attr(el, name):
    err, val = AXUIElementCopyAttributeValue(el, name, None)
    return val if err == 0 else None


def trusted() -> bool:
    return bool(AX_AVAILABLE and AXIsProcessTrusted())


def list_apps() -> list[dict]:
    """Running apps that have a UI (activationPolicy regular)."""
    out = []
    for a in NSWorkspace.sharedWorkspace().runningApplications():
        if a.activationPolicy() == 0:
            out.append({
                "name": _norm(a.localizedName()),
                "bundle": a.bundleIdentifier() or "",
                "pid": int(a.processIdentifier()),
            })
    return out


def frontmost() -> dict:
    """The app currently in front (so we can return to it after acting)."""
    a = NSWorkspace.sharedWorkspace().frontmostApplication()
    if a is None:
        return {}
    return {"name": _norm(a.localizedName()), "bundle": a.bundleIdentifier() or ""}


def activate(query: str) -> dict:
    """Bring a named app back to the front."""
    a = _resolve_app(query)
    if a is None:
        raise LookupError(f"app not running: {query}")
    a.activateWithOptions_(2)
    return {"activated": _norm(a.localizedName()), "bundle": a.bundleIdentifier() or ""}


def _resolve_app(query: str):
    q = (query or "").lower().strip()
    best = None
    for a in NSWorkspace.sharedWorkspace().runningApplications():
        name = _norm(a.localizedName()).lower()
        bundle = (a.bundleIdentifier() or "").lower()
        if not q:
            continue
        if q == name or q == bundle:
            return a
        if q in name or q in bundle:
            best = best or a
    return best


def _describe(el) -> dict:
    return {
        "role": _norm(_attr(el, "AXRole")),
        "title": _norm(_attr(el, "AXTitle")),
        "desc": _norm(_attr(el, "AXDescription")),
        "placeholder": _norm(_attr(el, "AXPlaceholderValue")),
        "value": _norm(_attr(el, "AXValue"))[:160],
    }


_SELECTOR_KEYS = (
    "role", "title", "desc",
    "title_contains", "desc_contains", "placeholder_contains", "value_contains",
)


def _has_selector(sel: dict) -> bool:
    return any(sel.get(k) for k in _SELECTOR_KEYS)


def _matches(d: dict, sel: dict) -> bool:
    if sel.get("role") and d["role"] != sel["role"]:
        return False
    if sel.get("title") and d["title"] != sel["title"]:
        return False
    if sel.get("desc") and d["desc"] != sel["desc"]:
        return False
    for field, key in (("title", "title_contains"), ("desc", "desc_contains"),
                       ("placeholder", "placeholder_contains"), ("value", "value_contains")):
        want = sel.get(key)
        if want and want.lower() not in d[field].lower():
            return False
    return True


def _collect(root, maxdepth: int, cap: int):
    """Iterative DFS over the AX tree → list of (element, described)."""
    out = []
    stack = [(root, 0)]
    while stack and len(out) < cap:
        el, depth = stack.pop()
        if el is None or depth > maxdepth:
            continue
        out.append((el, _describe(el)))
        kids = _attr(el, "AXChildren") or []
        for k in reversed(list(kids)):
            stack.append((k, depth + 1))
    return out


def find(app: str, sel: dict, limit: int = 40, maxdepth: int = 18,
         activate: bool = False) -> dict:
    if not AX_AVAILABLE:
        raise RuntimeError(f"accessibility unavailable: {AX_IMPORT_ERROR}")
    a = _resolve_app(app)
    if a is None:
        raise LookupError(f"app not running: {app}")
    if activate:
        a.activateWithOptions_(2)
        time.sleep(0.6)
    root = AXUIElementCreateApplication(a.processIdentifier())
    nodes = _collect(root, maxdepth, 6000)
    matches = [d for _, d in nodes if _matches(d, sel)] if _has_selector(sel) else [d for _, d in nodes]
    return {"app": _norm(a.localizedName()), "count": len(matches), "matches": matches[:limit]}


def act(app: str, sel: dict, action: str = "press", nth: int = 0,
        value: str | None = None, activate: bool = True, maxdepth: int = 18) -> dict:
    if not AX_AVAILABLE:
        raise RuntimeError(f"accessibility unavailable: {AX_IMPORT_ERROR}")
    if not _has_selector(sel):
        raise ValueError("act requires at least one selector (role/title/desc/*_contains)")
    a = _resolve_app(app)
    if a is None:
        raise LookupError(f"app not running: {app}")
    if activate:
        a.activateWithOptions_(2)
        time.sleep(0.6)
    root = AXUIElementCreateApplication(a.processIdentifier())
    nodes = _collect(root, maxdepth, 6000)
    matched = [(el, d) for el, d in nodes if _matches(d, sel)]
    if not matched:
        raise LookupError("no element matched the selector")
    if nth < 0 or nth >= len(matched):
        nth = 0
    el, d = matched[nth]
    if action == "press":
        AXUIElementPerformAction(el, "AXPress")
    elif action == "focus":
        AXUIElementSetAttributeValue(el, "AXFocused", True)
    elif action == "set_value":
        AXUIElementSetAttributeValue(el, "AXValue", value or "")
    else:
        raise ValueError(f"unknown action: {action!r} (use press|focus|set_value)")
    return {"ok": True, "action": action, "matched": d, "candidates": len(matched), "nth": nth}
