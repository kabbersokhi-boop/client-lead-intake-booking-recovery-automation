#!/usr/bin/env python3
"""Read-only checks required before a synthetic Phase 7 live run."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import HIGHLEVEL_LIVE_HOST, Settings  # noqa: E402
from app.providers.highlevel import HighLevelClient, HighLevelProviderError  # noqa: E402


def main() -> int:
    try:
        settings = Settings()
        if settings.crm_provider_mode != "highlevel_live":
            raise RuntimeError("CRM_PROVIDER_MODE must select highlevel_live.")
        if settings.highlevel_live_base_url != f"https://{HIGHLEVEL_LIVE_HOST}":
            raise RuntimeError("Live HighLevel target is not the pinned official host.")
        client = HighLevelClient(settings)
        try:
            body = client._request(
                "GET", f"/opportunities/pipelines/{settings.highlevel_pipeline_id}"
            )
            pipeline = body.get("pipeline", body)
            if (
                not isinstance(pipeline, dict)
                or pipeline.get("locationId") != settings.highlevel_location_id
                or pipeline.get("name") != "HVAC Service Pipeline"
            ):
                raise RuntimeError("The configured HVAC pipeline does not match the location.")
            stages = pipeline.get("stages")
            if not isinstance(stages, list) or [item.get("name") for item in stages] != [
                "New Lead", "Contacted", "Appointment Booked"
            ]:
                raise RuntimeError("The configured HVAC stage order does not match.")
            expected_ids = [
                settings.highlevel_stage_new_lead_id,
                settings.highlevel_stage_contacted_id,
                settings.highlevel_stage_appointment_booked_id,
            ]
            if [item.get("id") for item in stages] != expected_ids:
                raise RuntimeError("The configured HVAC stage IDs do not match.")
            for model, names in (
                ("contact", {
                    "HVAC Integration Submission ID": settings.highlevel_contact_submission_field_id,
                    "HVAC Integration Correlation ID": settings.highlevel_contact_correlation_field_id,
                }),
                ("opportunity", {
                    "HVAC Integration Opportunity Submission ID":
                        settings.highlevel_opportunity_submission_field_id,
                }),
            ):
                fields_body = client._request(
                    "GET", f"/locations/{settings.highlevel_location_id}/customFields",
                    params={"model": model},
                )
                fields = fields_body.get("customFields", fields_body.get("fields"))
                if not isinstance(fields, list):
                    raise RuntimeError("HighLevel custom field response was malformed.")
                for name, expected in names.items():
                    matches = [field for field in fields if field.get("name") == name]
                    if len(matches) != 1 or matches[0].get("id") != expected:
                        raise RuntimeError("A configured HighLevel identity field does not match.")
            print("Live mode, official host, location, HVAC pipeline, three stages, and identity fields verified.")
            return 0
        finally:
            client.client.close()
    except (HighLevelProviderError, RuntimeError, ValueError) as error:
        print(f"Phase 7 live preflight failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
