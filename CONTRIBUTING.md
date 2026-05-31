# Contributing to Olwen

Thanks for caring about Olwen.

This is a personal project at heart — built by one person — but help is
welcome wherever you see something rough or missing.

## Getting started

```bash
# 1. Clone
git clone https://github.com/moaaznaabilali/olwen.git
cd olwen

# 2. Backend — Python venv + deps
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt

# 3. Frontend — install deps
cd frontend && pnpm install && cd ..

# 4. Run both — backend on :8000, frontend on :3100
./start.sh
```

Then open <http://localhost:3100>. `./start.sh` runs both servers and
Ctrl-C stops them together.

### Opening a pull request

Fork, branch, and open a PR against `main`. Keep it small — one thing per
PR. See [Pull requests](#pull-requests) below for the full rhythm.

## Quick principles

- **Quiet by default.** Olwen never pings, beeps, or surprises. Any new
  feature should respect that. If it interrupts, it isn't shipping.
- **Show, don't shout.** The UI is the product, not the chat window.
  Build for the dashboard, not the prompt.
- **One sentence headlines.** Read your own copy out loud. If it
  doesn't feel like Olwen wrote it, rewrite.

## Code style

- **Python** — type hints, `async` where it matters, 88 cols, no
  pre-commit gymnastics. We follow conventional FastAPI patterns.
- **TypeScript** — Vue 3 `<script setup>` composition API only. Keep
  composables tiny and reactive (`useState` + `ref`). Avoid Pinia for now.
- **CSS** — scoped per component. Custom properties for theming. No
  Tailwind in the product (we want hand-tuned restraint).

## Pull requests

- Fork → branch → PR.
- Keep PRs small. One thing per PR.
- Tests aren't required but make the maintainer happier.
- Be patient — this isn't a full-time team.

## Reporting bugs

Open an issue. Include:

- What you were doing
- What Olwen did
- What you expected
- Browser + OS if it's a frontend bug
- Backend logs (last 30 lines) if it's a backend bug

## Feature requests

Open an issue, tag it `idea`. The most likely-to-ship features are:

- ✦ "Olwen could surface X, which I currently switch tabs for."
- ✦ "When I asked Olwen Y, he should have known to do Z."
- ✦ "The brief read like a list. It should have read like a person."

The least-likely-to-ship features are:

- ✦ Anything that adds a notification.
- ✦ Anything that interrupts a focus session.
- ✦ Anything that requires another login.

## License & contributions

By contributing you agree your changes are licensed under
[PolyForm Noncommercial 1.0.0](./LICENSE) — the same license as the rest
of the project.

For commercial-use questions: moaaznaabilali@gmail.com
