from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./lead_intake.db"
    n8n_webhook_url: str = "http://localhost:5678/webhook/lead-intake"
    n8n_request_timeout_ms: int = 15_000
    crm_adapter_api_key: SecretStr | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
