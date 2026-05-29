# Olwen Bridge

A tiny local daemon that gives Olwen control of your **mouse, keyboard, and
screen** on this device. Runs only on `127.0.0.1`, token-gated, never exposed
to the network.

## Install (macOS)

```bash
cd bridge
./install_bridge.sh
```

The installer:
- Drops the bridge into `~/.olwen/bridge/` with its own venv
- Creates a per-user **LaunchAgent** so the bridge starts at login
- Generates a random bearer token at `~/.olwen/bridge.token` (mode 0600)
- Prints the one manual step you can't automate: granting **Accessibility**
  permission to the Python interpreter

Linux (`systemd`) and Windows (`Task Scheduler`) installers are next.

## What it exposes

All endpoints require `Authorization: Bearer <token>`.

| Method | Path             | Body                                     |
|--------|------------------|------------------------------------------|
| GET    | `/health`        | —                                        |
| GET    | `/screen`        | —  → `{width, height, scale}`            |
| GET    | `/screenshot`    | —  → `image/png`                         |
| POST   | `/mouse/move`    | `{x, y, duration?}`                      |
| POST   | `/mouse/click`   | `{x?, y?, button?, count?, interval?}`   |
| POST   | `/mouse/scroll`  | `{dx, dy}`                               |
| POST   | `/key/type`      | `{text, interval?}`                      |
| POST   | `/key/press`     | `{keys: ["cmd","shift","p"]}`            |
| POST   | `/stop`          | — (no auth — the panic button)           |

`/stop` raises an in-memory flag that every other endpoint checks before
acting; in-flight pyautogui calls finish but no new action runs until the
flag self-clears after 500 ms.

## How Olwen uses it

```
   Claude (computer-use tool)
            ↓ "click at (842, 311)"
   Olwen backend
            ↓ POST /mouse/click  Authorization: Bearer …
   olwen-bridge (this daemon)
            ↓ pyautogui.click
   macOS
```

The user opens Computer-Use mode in the frontend; the backend pulls a
screenshot via `/screenshot`, ships it to Claude, executes the returned
tool calls against the bridge, repeats until done — with a live preview
and a STOP button on screen the entire time.

## Safety

- **127.0.0.1 only.** Uvicorn binds to localhost; no remote access.
- **Token auth.** Even other processes on your machine can't drive it without
  reading `~/.olwen/bridge.token` (mode 0600).
- **STOP button.** `POST /stop` works without auth — every endpoint honors
  the flag between actions.
- **No off-screen coords.** Pydantic schemas reject negatives.
- **Audit log.** Every action is logged to `~/.olwen/logs/bridge.out.log`.
- **macOS Accessibility prompt** — you grant the permission explicitly.

## Logs

```bash
tail -f ~/.olwen/logs/bridge.{out,err}.log
```

## Uninstall

```bash
./install_bridge.sh --uninstall
```

Unloads the LaunchAgent and removes `~/.olwen/bridge/`. The token file is
left in place so you can reinstall without breaking existing setups.
