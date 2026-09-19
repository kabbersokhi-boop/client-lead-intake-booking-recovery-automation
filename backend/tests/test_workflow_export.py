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
