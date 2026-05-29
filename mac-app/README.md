# Olwen.app

A real macOS application that hosts the Olwen Bridge — appears in the Dock
and Applications folder, opens a window showing live activity, and quits
through the menu like any other Mac app.

## Build

```bash
cd mac-app
./build.sh
```

That produces `dist/Olwen.app`. Drag it to `/Applications`.

Prereqs the build script installs into a local venv: `py2app`, PyObjC,
FastAPI, uvicorn, pyautogui, mss, pillow.

## What the app does

- Starts the bridge daemon on `127.0.0.1:8765` (localhost only)
- Opens a native window showing:
  - **Status pill** — `● bridge online`
  - **Token** — first/last chars + a **Copy token** button
  - **Recent activity** — last 60 actions (clicks, types, screenshots, …)
- Closing the window **hides it; the bridge keeps running**
- **⌘Q** quits the bridge

## First-time permission

macOS will ask for Accessibility access the first time Olwen tries to move
the cursor. Allow it from **System Settings → Privacy & Security →
Accessibility**. Without that, pyautogui silently does nothing.

## Files

- `olwen_app.py` — the app (PyObjC window + embedded bridge)
- `setup.py` — py2app config
- `build.sh` — one-command build
- `make_icon.sh` — generates `Olwen.icns` from the creature SVG
- `resources/` — icon + any future assets

## Uninstall

```bash
rm -rf /Applications/Olwen.app ~/.olwen
```
