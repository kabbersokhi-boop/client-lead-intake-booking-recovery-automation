from urllib.parse import urlsplit

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SIMULATOR_HOSTS = {"highlevel-simulator", "localhost", "127.0.0.1", "::1"}
HIGHLEVEL_LIVE_HOST = "services.leadconnectorhq.com"


class Settings(BaseSettings):
    database_url: str = "sqlite:///./lead_intake.db"
    n8n_webhook_url: str = "http://localhost:5678/webhook/lead-intake"
    n8n_booking_webhook_url: str = "http://localhost:5678/webhook/appointment-booking"
    n8n_editor_base_url: str = "http://localhost:5678"
    n8n_request_timeout_ms: int = 30_000
    crm_adapter_api_key: SecretStr | None = None
    crm_provider_mode: str = "development"
    highlevel_base_url: str = "http://highlevel-simulator:8080"
    highlevel_live_base_url: str = f"https://{HIGHLEVEL_LIVE_HOST}"
    highlevel_simulator_token: SecretStr | None = None
    highlevel_live_token: SecretStr | None = None
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

    @model_validator(mode="after")
    def validate_highlevel_target(self):
        if self.crm_provider_mode == "highlevel_live":
            if not self.highlevel_live_token:
                raise ValueError("HIGHLEVEL_LIVE_TOKEN is required in highlevel_live mode.")
            if self.highlevel_live_base_url != f"https://{HIGHLEVEL_LIVE_HOST}":
                raise ValueError(
                    "highlevel_live requires the official HTTPS HighLevel API host."
                )
            if not self.highlevel_location_id or self.highlevel_location_id.startswith("sim_"):
                raise ValueError(
                    "HIGHLEVEL_LOCATION_ID must be a real location ID in highlevel_live mode."
                )
            for field_name in (
                "highlevel_pipeline_id",
                "highlevel_stage_new_lead_id",
                "highlevel_stage_contacted_id",
                "highlevel_stage_appointment_booked_id",
                "highlevel_contact_submission_field_id",
                "highlevel_contact_correlation_field_id",
                "highlevel_opportunity_submission_field_id",
            ):
                value = getattr(self, field_name)
                if not value or value.startswith("sim_"):
                    raise ValueError(
                        f"{field_name.upper()} must be a real provisioned ID in "
                        "highlevel_live mode."
                    )
            return self
        if self.crm_provider_mode != "highlevel_simulator":
            return self
        if not self.highlevel_simulator_token:
            raise ValueError("HIGHLEVEL_SIMULATOR_TOKEN is required in highlevel_simulator mode.")
        base_url = self.highlevel_base_url
        try:
            parsed = urlsplit(base_url)
            port = parsed.port
        except ValueError as error:
            raise ValueError(
                "HIGHLEVEL_BASE_URL is invalid for highlevel_simulator mode."
            ) from error
        if (
            base_url != base_url.strip()
            or parsed.scheme != "http"
            or parsed.hostname not in SIMULATOR_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or port is None
        ):
            raise ValueError(
                "highlevel_simulator requires an explicit-port HTTP URL on "
                "highlevel-simulator, localhost, 127.0.0.1, or [::1], with no "
                "userinfo, path, query, or fragment."
            )
        return self


settings = Settings()
