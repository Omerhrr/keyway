from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/

class Settings(BaseSettings):
    APP_NAME: str = "Keyway API"
    ENV: str = "development"
    SECRET_KEY: str = "keyway-dev-secret-change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'db' / 'keyway.db'}"
    # LLM extraction micro-service (bun mini-service)
    LLM_SERVICE_URL: str = "http://127.0.0.1:8001"
    LLM_ENABLED: bool = True
    CORS_ORIGINS: str = "*"
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
        env_file = str(BASE_DIR / ".env")
        env_prefix = "KEYWAY_"

settings = Settings()

# Ensure the db directory exists
Path(settings.DATABASE_URL.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
