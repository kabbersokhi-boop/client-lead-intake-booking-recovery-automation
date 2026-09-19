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

## Timeout evidence and corrected request budget

| Field | Execution `146` observation |
| --- | --- |
| Caller | n8n workflow request |
| Model ID | `openai/gpt-oss-20b` |
| Start / stop | `2026-09-19T18:32:42.674Z` / `2026-09-19T18:32:52.771Z` |
| Elapsed | `10.097` seconds |
| Sanitized error | `ECONNABORTED` |
| Confirmed cause | The runtime had no NVIDIA timeout override, so the workflow's `10,000` ms default aborted the request. |
| Persistence result | Safe fallback persisted the lead; the workflow execution itself completed successfully. |

Three direct minimal synthetic requests completed in approximately `1.71`,
`5.23`, and `12.35` seconds. A synthetic request with `max_tokens=180`
returned HTTP `200` and schema-valid output in approximately `14.94` seconds.
The deployed workflow now uses `max_tokens=180` and an NVIDIA timeout of
`18,000` ms. The CRM timeout is `6,000` ms and the browser acknowledgement
budget is `30,000` ms, leaving explicit headroom while retaining fallback.

## Corrected live execution

| Field | Value |
| --- | --- |
| Caller | n8n execution `149` |
| Model ID | `openai/gpt-oss-20b` |
| Result | HTTP `201` intake response; `ai_status=enriched` |
| Validated extraction | `furnace_service`, `Surrey`, `Tuesday afternoon`, `medium` |
| Correlation ID | `f3dd6910-0aa8-4bfa-b281-46752617014f` |
| CRM / audit result | Lead `5c59bd59-1e12-41b4-a09e-dc40148649f8` persisted with one creation audit event. |

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
