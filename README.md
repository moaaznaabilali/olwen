<div align="center">

<br>

<img src="./site/public/creature.svg" alt="Olwen" width="260" />

<br>

# Olwen

**A calm AI companion that quietly knows everything.**

<sub>Reads your mail · Writes your morning · Runs your terminal · Stays out of your way</sub>

<br>

[![Site](https://img.shields.io/badge/site-olwenai.com-5EEAD4?style=flat-square&labelColor=02060A)](https://olwenai.com)
[![License: PolyForm NC 1.0.0](https://img.shields.io/badge/license-PolyForm%20NC%201.0.0-A7F3D0?style=flat-square&labelColor=02060A)](./LICENSE)
[![Status: Private beta](https://img.shields.io/badge/status-private%20beta-FBBF24?style=flat-square&labelColor=02060A)](#status)
[![Stack: Vue 3 · FastAPI · PostgreSQL](https://img.shields.io/badge/stack-Vue3%20·%20FastAPI%20·%20PostgreSQL-67E8F9?style=flat-square&labelColor=02060A)](#architecture)

</div>

<br>

> _"Most assistants shout. Olwen listens."_

Olwen is an ambient AI presence that lives at the edge of your screen.
He reads your inbox, watches your calendar, holds your tasks, runs your
terminal — and waits, patient, until you ask.

He's not a chat window. He's a creature.

<br>

## ✦ What he does

<table>
<tr>
<td width="50%" valign="top">

**Listens, all day, quietly**

Connect Gmail, Google Calendar, GitHub, and Strava. Olwen reads your
day without rules to write — what you skipped, who's waiting for a
reply, what you ran in the terminal yesterday.

</td>
<td width="50%" valign="top">

**Speaks once, with a voice**

A morning brief in his voice, 30 seconds: weather, the email that
matters, the task to start with, one news headline. Six sentences,
then quiet.

</td>
</tr>
<tr>
<td width="50%" valign="top">

**Acts when you ask**

_"Open my project with claude."_ He picks the right repo, opens Finder,
drops you into a terminal with Claude Code in dangerous mode. Eight
words → three actions → zero clicks.

</td>
<td width="50%" valign="top">

**Stays out of the way**

No notification storms. No daily nudges. No "Olwen wants to talk to
you." He breathes in the corner of the screen and waits.

</td>
</tr>
</table>

<br>

## ✦ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│    olwen/                                                   │
│    ├── backend/   FastAPI + async SQLAlchemy + PostgreSQL   │
│    │              Olwen's brain: integrations, AI, voice    │
│    │                                                        │
│    ├── frontend/  Nuxt 4 + Vue 3 + TypeScript               │
│    │              Olwen's body: dashboard, dev mode, apps   │
│    │                                                        │
│    └── site/      Vite + Vue + custom SVG                   │
│                   The marketing site (olwenai.com)          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Backend** is a modular monolith. Real subprocess control (PTY over
WebSocket so terminals stream live), real OAuth (Gmail/Calendar via
Google, GitHub PAT + OAuth, Strava OAuth), real LLM tool-calling
(Gemini function-calling with UI-action dispatch back to the frontend),
real server-side TTS (Edge neural voices streamed as MP3).

**Frontend** is Nuxt 4 with SSR off — runs as a single-page app. The
Olwen creature is hand-drawn SVG with tendrils that morph in real-time
toward your cursor. Dashboard widgets are individually toggleable. Apps
(terminal, browser, editor) live in floating draggable windows.

**Marketing site** is intentionally separate, intentionally tiny —
build output is 8 KB CSS + 36 KB JS gzipped.

<br>

## ✦ Senses

<table>
<tr>
<td>📨</td>
<td><b>Inbox</b></td>
<td>Triages your unread, ranks by urgency, suggests action per email. Olwen reads important ones aloud.</td>
</tr>
<tr>
<td>🗓</td>
<td><b>Calendar</b></td>
<td>Google Calendar primary, today + tomorrow. Marks events <code>soon</code> within 90 min.</td>
</tr>
<tr>
<td>✓</td>
<td><b>Tasks</b></td>
<td>Hand-written tasks with priority + list scoping. Cinematic review animation when you ask.</td>
</tr>
<tr>
<td>▢</td>
<td><b>Terminal</b></td>
<td>Real PTY on your host. Run claude, git, anything. Olwen can run commands himself.</td>
</tr>
<tr>
<td>⌗</td>
<td><b>Code</b></td>
<td>GitHub activity feed + local repo picker. <i>"Open my project with claude"</i> works.</td>
</tr>
<tr>
<td>✦</td>
<td><b>News</b></td>
<td>RSS topics you follow → 5 picks with one-line "why this matters" each.</td>
</tr>
<tr>
<td>♥</td>
<td><b>Body</b></td>
<td>Strava activities, training load. Olwen knows when you had a hard day.</td>
</tr>
<tr>
<td>⌖</td>
<td><b>Voice</b></td>
<td>Server-side TTS via Edge neural voices. Plays through a normal <code>&lt;audio&gt;</code> tag — works anywhere.</td>
</tr>
</table>

<br>

## ✦ The morning brief

Every morning, Olwen pulls his senses together and writes you the day
in 4–6 sentences. Then he reads it aloud:

> _"Good morning, Moaz. It's already 35 degrees in Riyadh — high of 44.
> Your evening holds Quran Werd at seven. The Q3 deck for Sarah needs
> your review, and a Google security alert is waiting. In the news,
> Anthropic raised $65B ahead of an IPO. Perhaps begin with Sarah's deck."_
>
> &nbsp;&nbsp;— Olwen · 07:58 AM · 31 seconds of neural audio

It fires once. No second one. No "evening summary." No "weekly digest."

<br>

## ✦ Dev mode

A pitch-black focus environment for coders. Say _"enter dev mode"_ — or
hit the keyboard shortcut — and the dashboard fades. Olwen and your
projects are all that remains.

Pick a project, and Olwen:

1. Opens the folder in Finder (`/usr/bin/open`)
2. Spawns a PTY in that directory
3. Auto-runs `claude --dangerously-skip-permissions`

Eight words, three actions, zero clicks.

<br>

## ✦ Tech stack

**Backend**
- Python 3.14, FastAPI, async SQLAlchemy 2.0
- PostgreSQL (will get pgvector for memory embeddings)
- Anthropic SDK / Google Gemini REST / Groq for LLMs
- `pty.fork()` + WebSockets for terminal streaming
- `edge-tts` for neural voice synthesis
- `feedparser` + `httpx` for news aggregation
- `aiosmtplib` for SMTP sending
- `imap-tools` for IMAP fallback

**Frontend (product)**
- Nuxt 4 / Vue 3 / TypeScript
- xterm.js for the terminal app (lazy-loaded)
- Hand-rolled SVG for the Olwen creature
- Web Speech API for browser TTS fallback
- IntersectionObserver-based reveals

**Marketing site**
- Vite + Vue 3 + TypeScript
- Custom SVG creature (same shape as the product)
- Hand-rolled motion (no GSAP) via rAF + IO

**Infrastructure**
- nginx + certbot (Let's Encrypt) for HTTPS
- Caddy where appropriate
- Single-host deployment for now (Ubuntu 24.04 in Riyadh)

<br>

## ✦ Install — one command

```bash
curl -fsSL https://raw.githubusercontent.com/moaaznaabilali/olwen/main/install.sh | bash
```

That's it. The installer clones the repo, sets up the Python venv, installs
backend + frontend dependencies, creates the Postgres database, generates a
random JWT secret, and writes a `start.sh` to launch everything.

When it finishes:

```bash
cd olwen
./start.sh
```

Then open **http://localhost:3100** — that's Olwen.

> **Prerequisites**: Python 3.11+, Node 20+, pnpm, PostgreSQL.
> macOS: `brew install python node pnpm postgresql@16 && brew services start postgresql@16`
> Ubuntu: `sudo apt install python3 python3-venv nodejs postgresql && npm i -g pnpm`

<br>

## ✦ How to use Olwen

### 1. Sign up

Open `http://localhost:3100`, click **Create account**, enter any email +
password. Olwen sends a 6-digit verification code — in dev mode it prints
to the **backend terminal** (no email key needed):

```
[email/console] OTP for you@example.com → 482193
```

Paste it back in the UI. You're in.

### 2. Give Olwen a brain (BYO key)

Settings → **AI provider** → paste your own:

- **Claude** key from <https://console.anthropic.com> (paid, best quality), or
- **Gemini** key from <https://aistudio.google.com/apikey> (free tier), or
- **Groq** key from <https://console.groq.com> (free, fastest)

You keep the key. It lives encrypted in your local Postgres.

### 3. Connect your life

From the dashboard, run the setup wizards (no env editing — credentials
go straight into the DB):

| Connect | What unlocks |
|--|--|
| **Gmail** (Google OAuth or IMAP) | Inbox triage, AI summaries, "read & reply with Olwen", morning brief |
| **Google Calendar** | Today's events in the dashboard + brief |
| **GitHub** (OAuth or PAT) | Repo activity widget, dev mode auto-context |
| **Strava** | Health/training widget |
| **News** (RSS) | Curated brief + cinematic "read with Olwen" mode |

### 4. Ask him to do something

The chat input at the bottom is Olwen. Try:

- *"What's my morning?"* → opens the cinematic brief
- *"Triage my inbox"* → opens email work mode
- *"Start a focus session on the olwen repo"* → opens dev mode + terminal
- *"Remember that I prefer mornings for deep work"* → writes to long-term memory

He's not a chat window — when he answers, he opens the right surface for
the task (inbox, calendar, terminal, brief) so you can act, not scroll.

### 5. Dev mode

Click the **terminal icon** in the dock (or say *"open dev mode"*). Pick a
project, and Olwen drops you into a black focus stage with a real PTY
terminal + an LLM that already knows your project context. Quit dev mode
with `⌘K` or `exit`.

### 6. Voice

Hold **Space** to push-to-talk, or toggle **Always listening** in Settings.
Olwen replies with a neural voice (Edge TTS, no API key needed).

<br>

## ✦ Manual install (if you skip the one-liner)

```bash
git clone https://github.com/moaaznaabilali/olwen.git && cd olwen
./install.sh        # same script, run locally
./start.sh
```

Or fully by hand: see [backend/README.md](./backend/README.md) and
[frontend/README.md](./frontend/README.md).

<br>

## ✦ Status

<div align="center">

| | |
|--|--|
| ✅ | Account system + Email OTP (Resend) |
| ✅ | Multi-provider LLM (Claude / Gemini / Groq, BYO key) |
| ✅ | Voice I/O (browser + server TTS) |
| ✅ | Tasks + cinematic review mode |
| ✅ | Memory store |
| ✅ | Skills marketplace + custom MCPs |
| ✅ | Gmail/IMAP universal email + triage + AI summarize + send/reply |
| ✅ | Google OAuth (calendar + gmail.modify) |
| ✅ | GitHub OAuth + PAT path |
| ✅ | Strava OAuth |
| ✅ | News RSS aggregator + "read with Olwen" cinematic |
| ✅ | Morning brief (auto-trigger + manual) |
| ✅ | Apps dock + real terminal app (PTY over WS) |
| ✅ | Dev mode (project picker + auto-Claude) |
| ✅ | Agent UI tools (Olwen opens his own surfaces) |
| 🚧 | Browser app + agent web automation |
| 🚧 | Editor app (Monaco + workspace files) |
| 🚧 | Mobile app |
| 🚧 | Multi-user / team deployment |

</div>

<br>

## ✦ License

This project is licensed under [**PolyForm Noncommercial 1.0.0**](./LICENSE).

In short:

- ✅ You can run Olwen for yourself, your hobby, your study, your charity, your school, your government work.
- ✅ You can modify it, fork it, share your fork.
- ✅ You can use it in research and publish what you learned.
- ❌ You can't sell Olwen, or a service built on Olwen, without a separate commercial license.
- ❌ You can't bundle Olwen into a paid SaaS, paid app, or revenue-generating product.

For commercial-use licensing, write to **moaaznaabilali@gmail.com**.

The license text is the long version. The vibe is: build with him for
yourself; don't make money off him.

<br>

## ✦ Credits

Created by [Moaz Nabil](https://olwenai.com) in Riyadh.

Olwen is shaped after the calm, ambient creatures of the deep — a small
luminous body, seven tendrils, and the discipline of patience.

<br>

<div align="center">

<sub>·</sub>

<sub>Olwen quietly knows everything.</sub>

<sub>·</sub>

</div>
