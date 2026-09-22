#!/usr/bin/env python3
"""Create and replay one synthetic HighLevel projection using configured live IDs.

The command is intentionally opt-in: it requires HIGHLEVEL_LIVE_TOKEN plus the
provisioned highlevel_live mapping environment variables.  It prints only synthetic
record identifiers and verification facts, never request headers or tokens.
"""

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from time import sleep

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.providers.highlevel import HighLevelClient, HighLevelProviderError  # noqa: E402
from app.schemas.lead import CRMLeadCreate  # noqa: E402


def payload() -> CRMLeadCreate:
    marker = uuid.uuid4()
    return CRMLeadCreate.model_validate(
        {
            "submission_id": marker,
            "correlation_id": uuid.uuid4(),
            "received_at": datetime.now(timezone.utc).isoformat(),
            "full_name": "Synthetic HVAC Live Verification",
            "email": f"synthetic-hvac-{marker.hex[:18]}@example.com",
            "phone": f"+1604555{int(marker.hex[:7], 16) % 10_000_000:07d}",
            "original_message": "Synthetic HighLevel integration verification only.",
            "normalized_message": "Synthetic HighLevel integration verification only.",
            "ai_status": "fallback_unavailable",
            "needs_review": True,
        }
    )


def main() -> int:
    try:
        settings = Settings()
        if settings.crm_provider_mode != "highlevel_live":
            raise RuntimeError("CRM_PROVIDER_MODE must be highlevel_live.")
        lead = payload()
        client = HighLevelClient(settings)
        client.sync_lead(lead)
        initial_contact = initial_opportunity = None
        # HighLevel's contact list is eventually consistent with contact creation. This
        # bounded verification poll never creates or updates another external effect.
        for _ in range(6):
            initial_contact = client._lookup_contact(lead)
            initial_opportunity = (
                client._lookup_opportunity(lead, initial_contact["id"])
                if initial_contact
                else None
            )
            if initial_contact and initial_opportunity:
                break
            sleep(2)
        if not initial_contact or not initial_opportunity:
            raise RuntimeError(
                "Initial live reconciliation did not find the created business effect "
                f"(contact_found={bool(initial_contact)}, "
                f"opportunity_found={bool(initial_opportunity)})."
            )
        client.sync_lead(lead)
        if not client.reconcile(lead):
            raise RuntimeError(
                "Replay live reconciliation did not find the existing business effect."
            )
        contact = client._lookup_contact(lead)
        if not contact:
            raise RuntimeError("Live contact lookup was unexpectedly absent after replay.")
        opportunity = client._lookup_opportunity(lead, contact["id"])
        if not opportunity:
            raise RuntimeError("Live opportunity lookup was unexpectedly absent after replay.")
        print(
            json.dumps(
                {
                    "submission_id": str(lead.submission_id),
                    "correlation_id": str(lead.correlation_id),
                    "contact_id": contact["id"],
                    "opportunity_id": opportunity["id"],
                    "location_id": settings.highlevel_location_id,
                    "pipeline_id": settings.highlevel_pipeline_id,
                    "stage_id": settings.highlevel_stage_new_lead_id,
                    "replay_reused_contact": True,
                    "replay_reused_opportunity": True,
                },
                sort_keys=True,
            )
        )
        return 0
    except (HighLevelProviderError, RuntimeError, ValueError) as error:
        print(f"verify_highlevel_live: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
