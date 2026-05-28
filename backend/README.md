# Olwen Backend

FastAPI backend for Olwen — a modular monolith (one app), stateless so it can
scale horizontally later. Phase: foundation (skeleton + accounts).

## Stack
- **FastAPI** + Uvicorn
- **PostgreSQL** via async SQLAlchemy 2.0 (`asyncpg`)
- **JWT** auth (access + refresh) with Argon2 password hashing (`pwdlib`)

## Prerequisites
- Python 3.12+ (tested on 3.14)
- PostgreSQL running, with a database named `olwen`
  (the default `DATABASE_URL` matches a local Postgres.app install)

## Setup
```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env          # then edit JWT_SECRET, DATABASE_URL if needed
```

## Run
```bash
.venv/bin/uvicorn app.main:app --reload --port 8000
```
- API: http://127.0.0.1:8000
- Interactive docs (Swagger): http://127.0.0.1:8000/docs

## Endpoints
| Method | Path                 | Auth | Purpose                          |
|--------|----------------------|------|----------------------------------|
| GET    | `/api/health`        | —    | Liveness + app info              |
| POST   | `/api/auth/register` | —    | Create account (email/password)  |
| POST   | `/api/auth/login`    | —    | Get access + refresh tokens      |
| POST   | `/api/auth/refresh`  | —    | Exchange refresh for new tokens  |
| GET    | `/api/users/me`      | ✅   | Current authenticated user       |

`login` uses the OAuth2 form (`username` = email, `password`), so the Swagger
**Authorize** button works for testing protected routes.

## Structure
```
app/
  main.py            FastAPI app, CORS, router wiring, startup
  core/
    config.py        Settings (pydantic-settings, .env)
    database.py      Async engine, session, Base, init_models()
    security.py      Password hashing + JWT helpers
  models/user.py     User ORM model
  schemas/user.py    Pydantic request/response schemas
  api/
    deps.py          get_current_user, session dependency
    routes/          health, auth, users
```

## Next steps (not built yet)
- Alembic migrations (currently tables are auto-created on startup)
- Google OAuth (slots into the auth module → also unlocks Gmail)
- Redis (sessions, rate limiting, WebSocket pub/sub when multi-instance)
- The AI brain: Claude streaming via SSE + entity events via WebSocket
