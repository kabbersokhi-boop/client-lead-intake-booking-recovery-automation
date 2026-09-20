const test = require("node:test");
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const path = require("node:path");

test("demo CLI rejects scope mismatch, checks business identity, and fails closed", () => {
  const code = String.raw`
import importlib.util
from pathlib import Path

script = Path.cwd() / "scripts/phase3_demo.py"
spec = importlib.util.spec_from_file_location("phase3_demo", script)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)

manifest = {
    "run_id": "11111111-1111-4111-8111-111111111111",
    "enquiries": [{
        "submission_id": "22222222-2222-4222-8222-222222222222",
        "correlation_id": "33333333-3333-4333-8333-333333333333",
        "full_name": "Alex Morgan",
        "email": "alex@example.com",
        "phone": "+1 604 555 0200",
        "message": "The furnace fan is noisy.",
    }],
}
item = manifest["enquiries"][0]

demo.request = lambda *args, **kwargs: (409, None)
demo.fault_state = lambda *args, **kwargs: {
    "submission_ids": ["44444444-4444-4444-8444-444444444444"],
    "request_limit": 5,
    "window_seconds": 10,
}
try:
    demo.register(manifest)
except RuntimeError as error:
    assert "does not match this manifest" in str(error)
else:
    raise AssertionError("mismatched existing run was accepted")

job_id = "55555555-5555-4555-8555-555555555555"
def state_request(url, **kwargs):
    if url.endswith("/api/recovery/jobs"):
        return 200, [{
            "id": job_id,
            "submission_id": item["submission_id"],
            "correlation_id": item["correlation_id"],
            "state": "completed",
            "completed_lead_id": "66666666-6666-4666-8666-666666666666",
        }]
    if url.endswith("/api/leads"):
        return 200, [{
            "id": "66666666-6666-4666-8666-666666666666",
            "submission_id": item["submission_id"],
            "correlation_id": item["correlation_id"],
            "full_name": "Wrong Name",
            "email": item["email"],
            "phone": item["phone"],
            "original_message": item["message"],
        }]
    if url.endswith(f"/api/recovery/jobs/{job_id}/attempts"):
        return 200, []
    raise AssertionError(url)
demo.request = state_request
demo.fault_state = lambda *args, **kwargs: None
state = demo.scoped_state(manifest)
assert state["identity_mismatches"] == [f"{item['submission_id']}:lead_business_data"]

controls = []
demo.control = lambda *args, **kwargs: controls.append(kwargs) or {}
def before_request(url, **kwargs):
    if url.endswith("/api/recovery/jobs") or url.endswith("/api/leads"):
        return 200, []
    return 500, {"message": "diagnostic failed without a CRM 429"}
demo.request = before_request
demo.scoped_state = lambda *args, **kwargs: {
    "expected": 1,
    "matching_leads": 0,
    "actual_write_attempts": [],
}
try:
    demo.before(manifest)
except RuntimeError as error:
    assert "partial CRM completion and a real 429" in str(error)
else:
    raise AssertionError("non-evidentiary diagnostic was accepted")
assert controls[-1] == {
    "active": False,
    "hold_delivery": False,
    "reset_window": True,
}
`;
  const python = process.env.PYTHON || "python3";
  const result = spawnSync(python, ["-c", code], {
    cwd: path.resolve(__dirname, "../.."),
    encoding: "utf8",
    timeout: 10000,
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
});
