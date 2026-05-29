"""Application configuration, loaded from environment / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Branding — entity name is configurable so "Olwen" can be renamed later.
    app_name: str = "Olwen"
    entity_name: str = "Olwen"
    environment: str = "development"

    # PostgreSQL (async). Default matches a local Postgres.app install.
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/olwen"

    # Auth
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    # Symmetric encryption key for secrets at rest (API keys, email passwords,
    # OAuth tokens). Set to a long random string in production. If empty, falls
    # back to JWT_SECRET — keeps old encrypted data readable until you migrate.
    encryption_key: str = ""

    # Login rate limit
    login_max_attempts: int = 5
    login_window_seconds: int = 300   # 5 min

    # Which brain powers Olwen by default: "gemini" (free tier) or "claude".
    # A user who connects their OWN Claude key always overrides this for them.
    llm_provider: str = "gemini"

    # Claude (paid API). Used if a user brings their own key, or as default
    # when llm_provider="claude". Empty everywhere -> mock streaming.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_max_tokens: int = 1024

    # Google Gemini (free tier). Get a free key at https://aistudio.google.com/apikey
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # Groq (fast, free tier). Get a free key at https://console.groq.com
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Brave Search API — free tier (2k queries/mo). https://api.search.brave.com
    # When set + a search skill is installed, Olwen can actually search the web.
    brave_api_key: str = ""

    # Google OAuth (Gmail "Sign in with Google" — one-click connect for users).
    # Get these by creating a Google Cloud OAuth client (Web). See README.
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/email/oauth/google/callback"
    google_post_oauth_redirect: str = "http://localhost:3100/?settings=email&connected=1"

    # GitHub OAuth — create an OAuth App at https://github.com/settings/developers
    # Callback URL = github_redirect_uri below.
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:8000/api/github/oauth/callback"
    github_post_oauth_redirect: str = "http://localhost:3100/?settings=connections&github=1"

    # Olwen Bridge — local daemon that controls mouse/keyboard/screen on the
    # user's own device. Lives at 127.0.0.1; never accept a non-loopback URL
    # in production. Token is read from a 0600 file the bridge writes at
    # install time.
    bridge_url: str = "http://127.0.0.1:8765"
    bridge_token_path: str = "~/.olwen/bridge.token"
    # Computer-use safety: max number of model→bridge action steps per task.
    # Prevents a runaway loop from chewing through your API budget or your
    # screen for an hour. 25 is enough for most real tasks.
    computer_use_max_steps: int = 25
    computer_use_model: str = "claude-sonnet-4-6"

    # Email OTP (signup verification)
    otp_expire_minutes: int = 10
    otp_max_attempts: int = 5
    # "console" = log the code (dev). "resend" = send real emails via Resend.
    email_provider: str = "console"
    resend_api_key: str = ""
    # Resend's shared test sender works without a verified domain, but can only
    # deliver to your own Resend account email. Use your domain for real users.
    email_from: str = "Olwen <onboarding@resend.dev>"

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"

    # CORS — the Nuxt dev origins.
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3100",
    ]


settings = Settings()
