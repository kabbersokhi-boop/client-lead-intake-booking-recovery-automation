# NVIDIA NIM diagnostic record

This is a sanitized incident and provider record. It intentionally excludes
keys, authorization headers, raw authenticated requests, and private URLs.

## Credential incident

The NVIDIA credential was exposed in the initial chat message and then placed
in a local Docker container environment during prior setup. It was also present
in command/tool context while that local container was created. It was **not**
found in tracked repository files or reachable Git history during the
2026-09-19 redacted scans. There is no evidence from those scans that it was
published to GitHub. The replacement n8n container has no `NVIDIA_*`
environment variables.

Deletion from a container is not remediation. The supplied key must be revoked
or rotated in NVIDIA's key-management interface before any further inference
attempt. A replacement must be placed only in local protected secret storage or
n8n credential/runtime configuration, never in chat, Git, a screenshot, a
frontend response, or an exported workflow.

## Current corrected-workflow observation

| Field | Value |
| --- | --- |
| Timestamp | 2026-09-19T17:45:27Z |
| Caller | n8n execution `143` |
| Endpoint | NVIDIA OpenAI-compatible `/v1/chat/completions` |
| Model ID | Unset after credential removal |
| HTTP status | Not available in n8n's sanitized node error |
| Error code | `ERR_BAD_REQUEST` |
| Request ID | Not available |
| Parameters | `model`, `temperature`, and `messages`; no JSON-format parameter |
| Observed conclusion | The workflow entered `fallback_unavailable` and persisted the lead. This is not evidence of inference authorization or entitlement. |

## Historical pre-remediation observations

Prior direct probes on 2026-09-19 observed HTTP `410` for
`meta/llama-3.1-8b-instruct` and `meta/llama-3.3-70b-instruct`, and HTTP `404`
for `nvidia/llama-3.1-nemotron-70b-instruct` and
`nv-mistralai/mistral-nemo-12b-instruct`. Those responses distinguish retired
or unavailable functions from an authorization decision; they do not establish
that the account lacks chat-inference entitlement. No further model probing was
performed for this correction.

## Required human action

1. Revoke the exposed NVIDIA API key in NVIDIA's API-key management interface.
2. Put a replacement in the existing local protected secret channel or n8n
   credential/runtime configuration, not in this repository or chat.
3. Select one currently available model from NVIDIA's current documentation.
4. Notify the operator that the protected runtime secret and model ID are set.

Verification succeeds only when one minimal, direct, synthetic
chat-completions request outside n8n returns a valid response using NVIDIA's
current official OpenAI-compatible example and supported parameters. The same
model and compatible request shape can then be configured in the workflow and
the browser-to-n8n-to-CRM flow rerun.
