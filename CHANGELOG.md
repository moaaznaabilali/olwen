# Changelog

All notable changes to Olwen are documented here.

## v0.3.1 — Olwen on Telegram

Olwen goes mobile. Link a Telegram bot and run your day — and start coding jobs —
from your phone.

### Added

- **Telegram link.** Connect a bot in **Settings → Connections → Telegram** (create
  it with @BotFather, paste the token, send `/start`), then text Olwen from anywhere:
  add or check tasks, send a WhatsApp, read your day, or kick off an unattended coding
  job — and he replies in the chat. It's a local long-polling bot (no public webhook),
  your token is stored encrypted, and only the chat you link can command him.
- **`queue_dev_job` tool** — start an unattended Dev Studio job straight from chat
  ("run a job in *my-site*: fix the failing tests") → Olwen opens a PR and pings you.
  Telegram becomes the mobile remote for the autonomy in v0.3.0.

### Fixed

- Unattended jobs now stash any pre-existing working-tree changes before branching,
  so a job's pull request contains only its own work.

## v0.3.0 — Dev Studio & unattended autonomy

Olwen stops being a tool you operate and becomes a teammate who works while you're
away. v0.3.0 turns the old project picker into **Dev Studio** — a project cockpit
where Olwen manages Claude Code for you, and can finish work, open a PR, and message
you when it's done, all without you watching.

### Added

- **Dev Studio** — a cockpit per project: movable/resizable terminal windows, the
  Olwen creature, and a live rail that reads the project's **git state + PRD/phases**
  ("where you stopped", recent commits, phase progress) from a new `/api/devmode/intel`.
- **Olwen orchestrates Claude Code.** Tell Olwen a goal in your own words — he
  *interprets* it like a brief to an engineer (typos and all), types it into the
  running Claude Code session, reads the terminal, and steers it to completion. The
  managing brain is cheap (Haiku); the actual coding is your Claude Code subscription.
- **Activity view** — a plain-language, live picture of what Claude Code is doing
  ("Looking at the site footer", "Building the project") for non-developers, plus an
  optional live preview of the project's running app. Zero extra tokens.
- **Unattended autonomy — give a goal, walk away, get a PR.** A server-side job
  runner runs `claude -p` headless on a fresh branch, commits, opens a PR, and pings
  you on WhatsApp when done. Jobs run in **parallel** (bounded pool) and survive the
  browser closing.
- **Reply-to-continue.** When a job genuinely needs a decision it goes *needs you*,
  asks a real question, and your reply (in the app, or over WhatsApp) **resumes the
  same Claude Code session** and finishes the work.
- **Guardrails for unattended runs.** A PreToolUse hook blocks anything irreversible
  or outward-facing — push to a remote/main, deploy/publish, `rm -rf`, `sudo`,
  `ssh`, database drops — even under bypass mode. Olwen alone pushes to a branch and
  opens a PR; nothing lands on main without your merge.
- **Live, resilient terminal.** The Dev Studio terminal auto-reconnects (and
  relaunches Claude Code) if the connection drops, so the session stays alive.

### Changed

- Picking a project drops straight into Dev Studio (no Finder pop — which on macOS
  yanked you to another Space).
- More forgiving intent routing now also catches coding intents ("let's code").

## v0.2.0 — Olwen learns to use your computer

The first release made Olwen a calm companion: a creature at the edge of your
screen that reads your day — tasks, inbox, calendar, news — and stays out of the
way until you ask. This release gives Olwen **hands**: with your permission, it can
now act on your Mac the way you would.

### Added

- **OS-level control via the Olwen Bridge.** A tiny local daemon (`127.0.0.1:8765`,
  bearer-token auth, loopback only) that moves the mouse, types, and reads the
  screen. Ships inside Olwen.app or runs standalone. A panic **STOP** is always one
  tap away.
- **"Give Olwen the wheel" (Computer Use).** Ask Olwen to do something on screen and
  it drives the desktop with Claude's vision, narrating each step — then hands
  control back and tells you what happened.
- **Deterministic app control via the macOS Accessibility API.** Instead of guessing
  pixels, Olwen finds the *real* UI elements by name — "the chat labelled X", "the
  message box" — and acts on them precisely. New bridge endpoints: `/ax/find`,
  `/ax/act`, `/ax/apps`, `/ax/frontmost`, `/ax/activate`. Instant, reliable, no
  tokens.
- **Send WhatsApp & Telegram messages.** "Message me on WhatsApp" now opens the right
  chat, types, sends — and **verifies the message actually landed** before saying so.
- **Action verification ("Olwen's eyes").** Real-world actions are confirmed against
  the screen/UI tree before Olwen claims success. No more "Sent!" when nothing sent.
- **Return-to-you.** After acting in another app, focus comes back to Olwen so you
  see the result.

### Changed

- `send_message` now drives WhatsApp through the Accessibility API (the old
  AppleScript/vision path is gone) — deterministic and self-verifying.
- Computer-use loop updated for current Claude models, with screenshot trimming and
  automatic back-off on rate limits so long tasks finish instead of failing.
- More forgiving intent routing — small typos and spacing ("whats app") still trigger
  the right action.

### Notes

- Controlling your Mac requires granting **Accessibility** permission once
  (System Settings → Privacy & Security → Accessibility). This cannot be automated
  by design — it's your machine, your consent.
- Everything runs locally. The bridge never leaves `127.0.0.1`.

## v0.1.0 — Initial public release

- The calm companion: breathing creature with cursor-reactive tendrils.
- Dashboard HUD: tasks, inbox, calendar, news, morning brief.
- Local backend (FastAPI + Postgres), full auth, bring-your-own-AI keys
  (Claude / Gemini / Groq).
- Web app, plus a native macOS app (WKWebView).
