"""Universal email via IMAP/SMTP — works with any provider.

Auto-detects common providers (Gmail, Outlook/Hotmail/Live, Yahoo, iCloud) so
users only paste their email + app-password. Reading uses imap-tools wrapped
in a thread (it's a sync lib); sending uses aiosmtplib.
"""
import asyncio
import re
from dataclasses import dataclass

from imap_tools import MailBox

# Domain → IMAP/SMTP defaults. Add more as needed.
_PROVIDERS: dict[str, tuple[str, int, str, int]] = {
    "gmail.com":        ("imap.gmail.com",          993, "smtp.gmail.com",          587),
    "googlemail.com":   ("imap.gmail.com",          993, "smtp.gmail.com",          587),
    "outlook.com":      ("outlook.office365.com",   993, "smtp.office365.com",      587),
    "hotmail.com":      ("outlook.office365.com",   993, "smtp.office365.com",      587),
    "live.com":         ("outlook.office365.com",   993, "smtp.office365.com",      587),
    "msn.com":          ("outlook.office365.com",   993, "smtp.office365.com",      587),
    "yahoo.com":        ("imap.mail.yahoo.com",     993, "smtp.mail.yahoo.com",     587),
    "icloud.com":       ("imap.mail.me.com",        993, "smtp.mail.me.com",        587),
    "me.com":           ("imap.mail.me.com",        993, "smtp.mail.me.com",        587),
    "mac.com":          ("imap.mail.me.com",        993, "smtp.mail.me.com",        587),
}


def detect_servers(email: str) -> tuple[str, int, str, int] | None:
    domain = email.lower().split("@")[-1].strip()
    return _PROVIDERS.get(domain)


@dataclass
class FetchedEmail:
    uid: str
    sender: str
    subject: str
    snippet: str
    date_iso: str
    unread: bool


def _safe_snippet(text: str, n: int = 280) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    return t[:n]


def _sync_login_ok(host: str, port: int, email: str, password: str) -> tuple[bool, str]:
    try:
        with MailBox(host, port).login(email, password, "INBOX"):
            return True, ""
    except Exception as exc:
        return False, str(exc)


async def login_ok(host: str, port: int, email: str, password: str) -> tuple[bool, str]:
    return await asyncio.to_thread(_sync_login_ok, host, port, email, password)


def _sync_fetch(host: str, port: int, email: str, password: str, limit: int) -> list[FetchedEmail]:
    out: list[FetchedEmail] = []
    with MailBox(host, port).login(email, password, "INBOX") as mb:
        # newest first; mark unread separately
        for msg in mb.fetch(reverse=True, limit=limit, mark_seen=False, bulk=True):
            out.append(FetchedEmail(
                uid=str(msg.uid or ""),
                sender=(msg.from_ or "").strip(),
                subject=(msg.subject or "(no subject)").strip(),
                snippet=_safe_snippet(msg.text or msg.html or ""),
                date_iso=msg.date.isoformat() if msg.date else "",
                unread=("\\Seen" not in (msg.flags or ())),
            ))
    return out


async def fetch_inbox(host: str, port: int, email: str, password: str, limit: int = 12) -> list[FetchedEmail]:
    return await asyncio.to_thread(_sync_fetch, host, port, email, password, limit)


@dataclass
class FullEmail:
    uid: str
    sender: str
    subject: str
    body: str  # plain text (HTML stripped if needed)
    date_iso: str
    unread: bool


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\n{3,}")


def _strip_html(html: str) -> str:
    txt = _TAG_RE.sub(" ", html or "")
    txt = re.sub(r"[ \t]+", " ", txt)
    return _WS_RE.sub("\n\n", txt).strip()


def _sync_fetch_one(host: str, port: int, email: str, password: str, uid: str) -> FullEmail | None:
    from imap_tools import AND
    with MailBox(host, port).login(email, password, "INBOX") as mb:
        for msg in mb.fetch(AND(uid=uid), mark_seen=False, limit=1):
            body = msg.text or _strip_html(msg.html or "")
            return FullEmail(
                uid=str(msg.uid or ""),
                sender=(msg.from_ or "").strip(),
                subject=(msg.subject or "(no subject)").strip(),
                body=body.strip(),
                date_iso=msg.date.isoformat() if msg.date else "",
                unread=("\\Seen" not in (msg.flags or ())),
            )
    return None


async def fetch_one(host: str, port: int, email: str, password: str, uid: str) -> FullEmail | None:
    return await asyncio.to_thread(_sync_fetch_one, host, port, email, password, uid)


def _sync_mark_read(host: str, port: int, email: str, password: str, uid: str) -> bool:
    from imap_tools import AND, MailBoxUnencrypted  # noqa: F401
    try:
        with MailBox(host, port).login(email, password, "INBOX") as mb:
            mb.flag([uid], "\\Seen", True)
        return True
    except Exception:
        return False


async def mark_read(host: str, port: int, email: str, password: str, uid: str) -> bool:
    return await asyncio.to_thread(_sync_mark_read, host, port, email, password, uid)


# ---------- SMTP send (for IMAP-connected accounts) ----------
from email.message import EmailMessage as _Msg          # noqa: E402

import aiosmtplib  # noqa: E402


async def send_smtp(
    smtp_host: str, smtp_port: int, from_addr: str, password: str,
    *, to: list[str], subject: str, body: str,
    in_reply_to: str | None = None, references: str | None = None,
) -> None:
    """Send a plain-text email via the provider's SMTP server.

    Standard STARTTLS on port 587. Raises on auth or transport failure.
    """
    msg = _Msg()
    msg["From"] = from_addr
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    msg.set_content(body)
    await aiosmtplib.send(
        msg,
        hostname=smtp_host, port=smtp_port,
        username=from_addr, password=password,
        start_tls=True,
    )
