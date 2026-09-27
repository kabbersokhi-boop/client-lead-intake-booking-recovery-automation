# Milestone 2A real-provider evaluation — protocol v2

- Coverage status: partial or not started across frozen splits; development 3/40 reserved, 3/40 settled; held_out 0/20 reserved, 0/20 settled.
- Dataset: synthetic-hvac-v2, 60 synthetic cases (40 development / 20 held out), effective dataset hash `d6780d5a945bf097cfe8dde076a30a7d6973308f7ab483234f54310e5a57b61b`.
- Dataset revision SHA-256: `fab3833ea2021e88c0ef3ed811399bf1a26d6f571b28cc9dc8b05e92a2977150`; rubric: synthetic-rubric-v2, SHA-256 `fb5e5fcc8743c7f0d0b0b73276f16a0af4132f6eeddfb9f1d55088dbc5b276cd`.
- Experiment ID: `50a029bdd95e42e753fd8a3be2af17f07ebb21d4c3eeb70611a55674ea37d321`; provider: nvidia_nim; model: openai/gpt-oss-20b; endpoint identity: https://integrate.api.nvidia.com/v1/chat/completions.
- Prompt SHA-256: `c95a8c1fbf4eae6ada2378d8e5ae7b23eef30f54fefccf1b3e2ceb688ba1b417`; exported validator/request contract SHA-256: `dddab8c7381379484225199bb868976ce599f0488c1cea1b8cccdbaf2dfbf5b7`; grader: milestone-2a-grader-v2.
- Effective request settings: `{"max_tokens":180,"reasoning_effort":"low","response_format":{"type":"json_object"},"temperature":0}`; execution policy: `{"concurrency":1,"failure_circuit_breaker":"3-consecutive-timeout-or-provider-failures","retries":0}`; timeout: 18000 ms.
- Attempts: 3; known legacy v1 provider observations are separate historical requests. Cost unavailable without a verified applicable rate.

### development (3/40 reservations)

- Provider availability (2xx / all reserved attempts): 0.0% (0/3)
- Schema-valid usable outputs (usable / 2xx): n/a (0/0)
- Automatic semantic agreement (correct / usable): n/a (0/0)
- Overall success (correct / all reserved attempts): 0.0% (0/3)
- Outcomes: usable_output 0, invalid_output 0, timeout 3, provider_failure 0, unknown_request_outcome 0
- Token usage: returned on 0/3 attempts; prompt unavailable (0 returned), completion unavailable (0 returned), total unavailable (0 returned); missing usage is unavailable, not zero per response. Cost unavailable unless a verified applicable rate is supplied.
- Summary review required for 0/0 usable outputs. Prose lexical signals are review cues only and do not affect structured-field accuracy.

| Field | Correct / automatically scored usable outputs |
|---|---:|
| service_type | n/a (0/0) |
| location | n/a (0/0) |
| preferred_time | n/a (0/0) |
| urgency | n/a (0/0) |

| Category | Automatic successes / attempted (cases in split) |
|---|---:|
| straightforward | 0/3 (8 cases) |
| missing_and_paraphrase | 0/0 (8 cases) |
| ambiguity_and_conflict | 0/0 (8 cases) |
| urgency_policy | 0/0 (8 cases) |
| unsupported_and_adversarial | 0/0 (8 cases) |

## Representative failures

- **S001 (timeout)**: expected {"service_type":"furnace_service","location":"Surrey","preferred_time":"Tuesday afternoon","urgency":"high"}; extracted null; fields {}; error timeout.
- **S002 (timeout)**: expected {"service_type":"air_conditioning_service","location":"Burnaby","preferred_time":"Friday morning","urgency":"medium"}; extracted null; fields {}; error timeout.
- **S003 (timeout)**: expected {"service_type":"plumbing_service","location":"Coquitlam","preferred_time":"Tomorrow after lunch","urgency":"high"}; extracted null; fields {}; error timeout.

## Interpretation and limitations

This is mechanical agreement with a hand-authored synthetic dataset, not production accuracy, ROI, or human validation. Labels were AI-assisted-reviewed but are not independent human ground truth. Urgency is a synthetic business convention, not clinical or professionally validated safety guidance. The v2 overlay corrects S001 and M002 to high urgency under the explicit no-heat rule; every change is documented. The v1 ledger and published v1 results are preserved unchanged.

The prose claim detector only raises a human-review flag for selected lexical cues; it cannot distinguish customer availability, negation, quotation, or provider assertions. Structured semantic scores are unaffected by this flag. Summaries always require review. Location and time grading remains conservative exact normalized equality.

## Reproduction

```bash
node scripts/ai-evaluation-v2.mjs validate
npm run test:evaluation
bash scripts/ai-evaluation-via-n8n.sh run --split development --run-id baseline-v2-development
bash scripts/ai-evaluation-via-n8n.sh run --split development --run-id baseline-v2-development --ack-circuit-reset  # only after diagnosing a transient failure
bash scripts/ai-evaluation-via-n8n.sh run --split held_out --run-id baseline-v2-held_out  # only after all development cases settle
node scripts/ai-evaluation-v2.mjs report
```

The circuit breaker opens after three consecutive timeout/provider failures. It stops new reservations; settled and uncertain case IDs are never retried. `--ack-circuit-reset` applies only to unreserved cases and should be used only after an operator diagnoses a transient service issue. Held-out calls are gated on all development cases having settled outcomes.
