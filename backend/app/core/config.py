from pathlib import Path
from pydantic import model_validator
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/

_DEV_SECRET = "keyway-dev-secret-change-me"


class Settings(BaseSettings):
    APP_NAME: str = "Keyway API"
    ENV: str = "development"
    SECRET_KEY: str = _DEV_SECRET
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'db' / 'keyway.db'}"
    # Where inbound WhatsApp media is stored (default: next to the SQLite file)
    MEDIA_DIR: str = ""
    # LLM extraction micro-service (bun mini-service)
    LLM_SERVICE_URL: str = "http://127.0.0.1:8001"
    LLM_ENABLED: bool = True
    CORS_ORIGINS: str = "*"
    # ---- first-boot admin for PRODUCTION (no demo data is ever seeded there) ----
    BOOTSTRAP_ADMIN_EMAIL: str = ""
    BOOTSTRAP_ADMIN_PASSWORD: str = ""
    BOOTSTRAP_ADMIN_NAME: str = "Administrator"
    # ---- WhatsApp Cloud API (Phase 6A) ----
    # Effective mode lives on the WhatsAppAccount DB row (editable in Settings UI);
    # these env values seed/override credentials for headless deployments.
    # Simulated vendor messages remain available regardless of mode.
    WHATSAPP_MODE: str = "SIMULATOR"            # SIMULATOR | CLOUD_API
    WHATSAPP_ACCESS_TOKEN: str = ""             # permanent/long-lived system-user token
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_WABA_ID: str = ""
    WHATSAPP_APP_SECRET: str = ""               # for X-Hub-Signature-256 verification
    WHATSAPP_VERIFY_TOKEN: str = "keyway-verify"
    WHATSAPP_API_VERSION: str = "v21.0"

    class Config:
        # NOTE: every variable carries the KEYWAY_ prefix, e.g. KEYWAY_DATABASE_URL.
        env_file = str(BASE_DIR / ".env")
        env_prefix = "KEYWAY_"
        extra = "ignore"

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() == "production"

    @property
    def sqlite_path(self) -> Path | None:
        """Filesystem path of the SQLite database, or None for other databases."""
        url = self.DATABASE_URL
        if url.startswith("sqlite:///"):
            p = Path(url[len("sqlite:///"):])
            return p if p.is_absolute() else (BASE_DIR / p)
        return None

    @property
    def media_dir(self) -> Path:
        if self.MEDIA_DIR:
            return Path(self.MEDIA_DIR)
        sp = self.sqlite_path
        return (sp.parent if sp else BASE_DIR / "db") / "media"

    @model_validator(mode="after")
    def _production_guards(self):
        """Fail fast instead of booting a production system that anyone can break into."""
        if self.is_production:
            problems = []
            if self.SECRET_KEY == _DEV_SECRET or len(self.SECRET_KEY) < 32:
                problems.append("KEYWAY_SECRET_KEY must be a random string of at least 32 characters")
            if self.CORS_ORIGINS.strip() == "*":
                problems.append("KEYWAY_CORS_ORIGINS must list your exact dashboard origin(s), not '*'")
            if problems:
                raise ValueError("Refusing to start in production: " + "; ".join(problems))
        return self


settings = Settings()

# Ensure the SQLite directory exists (only for sqlite - never derive paths from other URLs)
if settings.sqlite_path is not None:
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
