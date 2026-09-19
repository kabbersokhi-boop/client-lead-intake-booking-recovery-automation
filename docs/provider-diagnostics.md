# NVIDIA NIM diagnostic record

This is a sanitized incident and provider record. It intentionally excludes
keys, authorization headers, raw authenticated requests, and private URLs.

## Credential incident

The NVIDIA credential was exposed in the initial chat message and then placed
in a local Docker container environment during prior setup. It was also present
in command/tool context while that local container was created. It was **not**
found in tracked repository files or reachable Git history during the
2026-09-19 redacted scans. There is no evidence from those scans that it was
published to GitHub. The recreated n8n container reads its replacement runtime
configuration from protected local storage; values are not retained here.

Deletion from a container is not remediation. The supplied key must be revoked
or rotated in NVIDIA's key-management interface before any further inference
attempt. A replacement must be placed only in local protected secret storage or
n8n credential/runtime configuration, never in chat, Git, a screenshot, a
frontend response, or an exported workflow.

## Live verification after credential rotation

| Field | Direct request | n8n workflow request |
| --- | --- | --- |
| Timestamp | 2026-09-19; exact request timestamp not retained | 2026-09-19T18:22:33Z |
| Caller | Direct synthetic check | n8n execution `145` |
| Endpoint | NVIDIA OpenAI-compatible `/v1/chat/completions` | NVIDIA OpenAI-compatible `/v1/chat/completions` |
| Model ID | `openai/gpt-oss-20b` | `openai/gpt-oss-20b` |
| HTTP status | `200` | `200` persisted in safe provider metadata |
| Request / response reference | `chatcmpl-9228e2f658a7f0d8` | n8n execution `145` |
| Parameters | `model`, `temperature`, and `messages` | `model`, `temperature`, and `messages` |
| Result | Non-empty chat response | Schema-valid enriched service context persisted through the development CRM adapter |

The direct request used synthetic text only. Neither request stored or exposed
an authorization header, token, or API key in repository files, workflow
exports, documentation, or browser content.

## Historical fallback observation

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

## Ongoing key handling

The replacement key remains only in protected local runtime storage. Keep it
out of chat, Git, screenshots, browser responses, n8n workflow exports, and
command output. Rotation/revocation remains the required remediation for the
previously exposed key.
