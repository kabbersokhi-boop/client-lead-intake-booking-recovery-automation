from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./lead_intake.db"
    n8n_webhook_url: str = "http://localhost:5678/webhook/lead-intake"
    n8n_booking_webhook_url: str = "http://localhost:5678/webhook/appointment-booking"
    n8n_editor_base_url: str = "http://localhost:5678"
    n8n_request_timeout_ms: int = 30_000
    crm_adapter_api_key: SecretStr | None = None
    follow_up_delay_seconds: int = 120
    business_timezone: str = "America/Vancouver"
    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    development_email_from: str = "automation-demo@example.test"
    crm_recovery_max_attempts: int = 4
    crm_recovery_lease_seconds: int = 30
    crm_retry_fallback_seconds: int = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
