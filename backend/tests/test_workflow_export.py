import json
from pathlib import Path


def test_sanitized_workflow_has_required_safety_controls():
    export_path = Path(__file__).resolve().parents[2] / "n8n" / "lead-intake.json"
    workflow = json.loads(export_path.read_text())
    serialized = json.dumps(workflow)
    nodes = {node["name"]: node for node in workflow["nodes"]}

    assert workflow["name"] == "Lead Intake - Validation, AI Enrichment and CRM Persistence"
    assert "nvapi-" not in serialized.lower()
    assert "x-n8n-api-key" not in serialized.lower()
    assert all("credentials" not in node for node in workflow["nodes"])

    validation_code = nodes["Validate Required Fields"]["parameters"]["jsCode"]
    assert "JSON.parse(rawRequest)" in validation_code
    assert "Full name is required." in validation_code
    assert "An email address or phone number is required." in validation_code

    ai_validation_code = nodes["Validate AI Extraction"]["parameters"]["jsCode"]
    assert "fallback_invalid" in ai_validation_code
    assert "fallback_unavailable" in ai_validation_code

    nvidia_request = nodes["Extract Service Context with NVIDIA NIM"]["parameters"]
    assert nvidia_request["options"]["timeout"] == (
        "={{ Number($env.NVIDIA_NIM_TIMEOUT_MS || 18000) }}"
    )
    assert "max_tokens: 180" in nvidia_request["jsonBody"]

    crm_request = nodes["Create CRM Lead"]["parameters"]
    assert crm_request["options"]["timeout"] == "={{ Number($env.CRM_ADAPTER_TIMEOUT_MS || 6000) }}"

    success_options = nodes["Return Enquiry Result"]["parameters"]["options"]
    headers = success_options["responseHeaders"]["entries"]
    response_headers = {header["name"]: header["value"] for header in headers}
    assert response_headers["Access-Control-Allow-Origin"] == "http://localhost:18000"


def test_phase_two_workflows_are_sanitized_and_use_semantic_boundaries():
    export_dir = Path(__file__).resolve().parents[2] / "n8n"
    booking = json.loads((export_dir / "appointment-booking.json").read_text())
    follow_up = json.loads((export_dir / "follow-up-dispatch.json").read_text())

    for workflow in [booking, follow_up]:
        serialized = json.dumps(workflow).lower()
        assert "nvapi-" not in serialized
        assert "x-n8n-api-key" not in serialized
        assert all("credentials" not in node for node in workflow["nodes"])

    booking_nodes = {node["name"]: node for node in booking["nodes"]}
    assert booking["name"] == "Lifecycle - Appointment Booking and Confirmation"
    assert "Validate Booking Request" in booking_nodes
    assert "Create Appointment and Transition Lifecycle" in booking_nodes
    assert "Send Booking Confirmation Test Email" in booking_nodes
    assert "America/Vancouver" in booking_nodes["Validate Booking Request"]["parameters"][
        "jsCode"
    ]

    follow_up_nodes = {node["name"]: node for node in follow_up["nodes"]}
    assert follow_up["name"] == "Lifecycle - Dispatch Due Follow-ups"
    assert follow_up_nodes["Check Every Minute"]["type"] == "n8n-nodes-base.scheduleTrigger"
    assert "follow-ups/due" in follow_up_nodes["Fetch Due Pending Follow-ups"]["parameters"][
        "url"
    ]
