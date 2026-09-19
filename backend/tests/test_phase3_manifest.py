import json
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.lead import CRMLeadCreate


def test_phase3_manifest_has_twelve_unique_contract_valid_enquiries():
    path = Path(__file__).resolve().parents[2] / "docs/fixtures/phase-3-manifest.json"
    manifest = json.loads(path.read_text())
    enquiries = manifest["enquiries"]
    assert len(enquiries) == 12
    assert len({item["submission_id"] for item in enquiries}) == 12
    assert len({item["correlation_id"] for item in enquiries}) == 12
    for enquiry in enquiries:
        CRMLeadCreate.model_validate(
            {
                **{key: value for key, value in enquiry.items() if key != "message"},
                "received_at": datetime.now(timezone.utc).isoformat(),
                "original_message": enquiry["message"],
                "normalized_message": enquiry["message"],
                "enrichment": None,
                "ai_status": "fallback_unavailable",
                "needs_review": True,
            }
        )
