from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./lead_intake.db"
    n8n_webhook_url: str = "http://localhost:5678/webhook/lead-intake"
    n8n_booking_webhook_url: str = "http://localhost:5678/webhook/appointment-booking"
    n8n_editor_base_url: str = "http://localhost:5678"
    n8n_request_timeout_ms: int = 30_000
    crm_adapter_api_key: SecretStr | None = None
    crm_provider_mode: str = "development"
    highlevel_base_url: str = "http://highlevel-simulator:8080"
    highlevel_token: SecretStr | None = None
    highlevel_location_id: str = "sim_location_reference"
    highlevel_pipeline_id: str = "sim_pipeline_hvac"
    highlevel_stage_new_lead_id: str = "sim_stage_new_lead"
    highlevel_stage_contacted_id: str = "sim_stage_contacted"
    highlevel_stage_appointment_booked_id: str = "sim_stage_appointment_booked"
    highlevel_contact_submission_field_id: str = "sim_cf_submission_id"
    highlevel_contact_correlation_field_id: str = "sim_cf_correlation_id"
    highlevel_opportunity_submission_field_id: str = "sim_of_submission_id"
    highlevel_timeout_seconds: float = 2.0
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
