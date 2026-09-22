#!/usr/bin/env python3
"""Repair only interrupted Phase 6 synthetic HighLevel projections.

Default mode is read-only.  ``--apply`` is intentionally required before creating
an opportunity, and the command refuses any record that is not marked by all
three integration identity fields and the dedicated synthetic-email namespace.
"""

import argparse
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


def synthetic_payload(
    client: HighLevelClient, contact: dict[str, object]
) -> CRMLeadCreate | None:
    fields = contact.get("customFields")
    if not isinstance(fields, list):
        return None
    submission = client._field_value(
        contact, client.settings.highlevel_contact_submission_field_id
    )
    correlation = client._field_value(
        contact, client.settings.highlevel_contact_correlation_field_id
    )
    first_name = contact.get("firstName")
    last_name = contact.get("lastName")
    email = contact.get("email")
    phone = contact.get("phone")
    if (
        not isinstance(submission, str)
        or not isinstance(correlation, str)
        or not isinstance(first_name, str)
        or not isinstance(last_name, str)
        or not isinstance(email, str)
        or not email.startswith("synthetic-hvac-")
        or not email.endswith("@example.com")
        or not isinstance(phone, str)
    ):
        return None
    try:
        return CRMLeadCreate.model_validate(
            {
                "submission_id": uuid.UUID(submission),
                "correlation_id": uuid.UUID(correlation),
                "received_at": datetime.now(timezone.utc).isoformat(),
                "full_name": f"{first_name} {last_name}".strip(),
                "email": email,
                "phone": phone,
                "original_message": "Synthetic HighLevel reconciliation only.",
                "normalized_message": "Synthetic HighLevel reconciliation only.",
                "ai_status": "fallback_unavailable",
                "needs_review": True,
            }
        )
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="create only a verified-missing opportunity for an eligible synthetic contact",
    )
    parser.add_argument(
        "--verify-replay",
        action="store_true",
        help="prove existing eligible effects reconcile without allowing any external write",
    )
    args = parser.parse_args()
    try:
        settings = Settings()
        if settings.crm_provider_mode != "highlevel_live":
            raise RuntimeError("CRM_PROVIDER_MODE must be highlevel_live.")
        client = HighLevelClient(settings)
        scanned = eligible = complete = missing = repaired = replay_zero_write_verified = 0
        for contact in client._list_live_contacts():
            scanned += 1
            payload = synthetic_payload(client, contact)
            if payload is None:
                continue
            eligible += 1
            contact_id = contact.get("id")
            if not isinstance(contact_id, str):
                raise RuntimeError("Eligible synthetic contact did not include an ID.")
            opportunity = client._lookup_opportunity(payload, contact_id)
            if opportunity:
                complete += 1
                if args.verify_replay:
                    original_request = client._request

                    def read_only_request(method: str, path: str, **kwargs: object) -> dict:
                        if method != "GET":
                            raise RuntimeError(
                                "Replay would issue an unexpected external write."
                            )
                        return original_request(method, path, **kwargs)

                    client._request = read_only_request  # type: ignore[method-assign]
                    try:
                        client.sync_lead(payload)
                    finally:
                        client._request = original_request  # type: ignore[method-assign]
                    replay_zero_write_verified += 1
                continue
            missing += 1
            if args.apply:
                # sync_lead reuses the verified application-owned contact and creates only
                # the absent opportunity. It never updates the contact in this branch.
                client.sync_lead(payload)
                for _ in range(6):
                    if client._lookup_opportunity(payload, contact_id):
                        break
                    sleep(2)
                else:
                    raise RuntimeError("Opportunity did not reconcile after the guarded repair.")
                repaired += 1
        print(
            json.dumps(
                {
                    "mode": "apply" if args.apply else "dry_run",
                    "contacts_scanned": scanned,
                    "eligible_synthetic_contacts": eligible,
                    "complete_effects": complete,
                    "missing_opportunities": missing,
                    "opportunities_repaired": repaired,
                    # _lookup_opportunity raises instead of returning for duplicate
                    # submission IDs or wrong contact/pipeline linkage.
                    "duplicate_submission_identity_conflicts": 0,
                    "zero_write_replays_verified": replay_zero_write_verified,
                },
                sort_keys=True,
            )
        )
        return 0
    except (HighLevelProviderError, RuntimeError, ValueError) as error:
        print(f"reconcile_highlevel_live_synthetics: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
