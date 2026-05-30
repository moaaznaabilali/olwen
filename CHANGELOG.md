# Changelog

All notable changes to Olwen are documented here.

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
