# Milestone 2A real-provider evaluation — protocol v2

- Coverage status: complete across both frozen splits; development 40/40 reserved, 40/40 settled; held_out 20/20 reserved, 20/20 settled.
- Dataset: synthetic-hvac-v2, 60 synthetic cases (40 development / 20 held out), effective dataset hash `d6780d5a945bf097cfe8dde076a30a7d6973308f7ab483234f54310e5a57b61b`.
- Dataset revision SHA-256: `fab3833ea2021e88c0ef3ed811399bf1a26d6f571b28cc9dc8b05e92a2977150`; rubric: synthetic-rubric-v2, SHA-256 `fb5e5fcc8743c7f0d0b0b73276f16a0af4132f6eeddfb9f1d55088dbc5b276cd`.
- Experiment ID: `0c2f59c02da9141f84f6304754acf9005e4459bd157f3dba8fbf333323ee0876`; provider: nvidia_nim; model: nvidia/nemotron-3.5-lightning-30b-a3b; endpoint identity: https://integrate.api.nvidia.com/v1/chat/completions.
- Prompt SHA-256: `c95a8c1fbf4eae6ada2378d8e5ae7b23eef30f54fefccf1b3e2ceb688ba1b417`; exported validator/request contract SHA-256: `dddab8c7381379484225199bb868976ce599f0488c1cea1b8cccdbaf2dfbf5b7`; grader: milestone-2a-grader-v2.
- Effective request settings: `{"max_tokens":512,"reasoning_budget":0,"response_format":{"type":"json_object"},"stream":false,"temperature":0}`; execution policy: `{"concurrency":1,"failure_circuit_breaker":"3-consecutive-timeout-or-provider-failures","retries":0}`; timeout: 18000 ms.
- Attempts: 60; known legacy v1 provider observations are separate historical requests. Cost unavailable without a verified applicable rate.

### development (40/40 reservations)

- Provider availability (2xx / all reserved attempts): 97.5% (39/40)
- Schema-valid usable outputs (usable / 2xx): 94.9% (37/39)
- Automatic semantic agreement (correct / usable): 24.3% (9/37)
- Overall success (correct / all reserved attempts): 22.5% (9/40)
- Outcomes: usable_output 37, invalid_output 2, timeout 1, provider_failure 0, unknown_request_outcome 0
- Token usage: returned on 39/40 attempts; prompt 4151 across 39, completion 2207 across 39, total 6358 across 39; missing usage is unavailable, not zero per response. Cost unavailable unless a verified applicable rate is supplied.
- Summary review required for 37/37 usable outputs. Prose lexical signals are review cues only and do not affect structured-field accuracy.

| Field | Correct / automatically scored usable outputs |
|---|---:|
| service_type | 89.2% (33/37) |
| location | 91.9% (34/37) |
| preferred_time | 70.3% (26/37) |
| urgency | 59.5% (22/37) |

| Category | Automatic successes / attempted (cases in split) |
|---|---:|
| straightforward | 3/8 (8 cases) |
| missing_and_paraphrase | 1/8 (8 cases) |
| ambiguity_and_conflict | 1/8 (8 cases) |
| urgency_policy | 4/8 (8 cases) |
| unsupported_and_adversarial | 0/8 (8 cases) |

### held_out (20/20 reservations)

- Provider availability (2xx / all reserved attempts): 95.0% (19/20)
- Schema-valid usable outputs (usable / 2xx): 100.0% (19/19)
- Automatic semantic agreement (correct / usable): 31.6% (6/19)
- Overall success (correct / all reserved attempts): 30.0% (6/20)
- Outcomes: usable_output 19, invalid_output 0, timeout 1, provider_failure 0, unknown_request_outcome 0
- Token usage: returned on 19/20 attempts; prompt 2093 across 19, completion 1146 across 19, total 3239 across 19; missing usage is unavailable, not zero per response. Cost unavailable unless a verified applicable rate is supplied.
- Summary review required for 19/19 usable outputs. Prose lexical signals are review cues only and do not affect structured-field accuracy.

| Field | Correct / automatically scored usable outputs |
|---|---:|
| service_type | 73.7% (14/19) |
| location | 89.5% (17/19) |
| preferred_time | 73.7% (14/19) |
| urgency | 52.6% (10/19) |

| Category | Automatic successes / attempted (cases in split) |
|---|---:|
| missing_and_paraphrase | 1/5 (5 cases) |
| ambiguity_and_conflict | 1/6 (6 cases) |
| urgency_policy | 4/5 (5 cases) |
| unsupported_and_adversarial | 0/4 (4 cases) |

## Representative failures

- **S001 (usable_output)**: expected {"service_type":"furnace_service","location":"Surrey","preferred_time":"Tuesday afternoon","urgency":"high"}; extracted {"service_type":"furnace_service","location":"Surrey","preferred_time":"Tuesday afternoon","urgency":"medium","summary":"Furnace stopped heating"}; fields {"service_type":true,"location":true,"preferred_time":true,"urgency":false}; error none.
- **S003 (usable_output)**: expected {"service_type":"plumbing_service","location":"Coquitlam","preferred_time":"Tomorrow after lunch","urgency":"high"}; extracted {"service_type":"plumbing_service","location":"Coquitlam","preferred_time":"Tomorrow after lunch","urgency":"medium","summary":"Pipe under kitchen sink is leaking"}; fields {"service_type":true,"location":true,"preferred_time":true,"urgency":false}; error none.
- **S004 (usable_output)**: expected {"service_type":"electrical_service","location":"Richmond","preferred_time":"Today","urgency":"urgent"}; extracted {"service_type":"electrical_service","location":"Richmond office","preferred_time":"today","urgency":"urgent","summary":"The outlet in my Richmond office is sparking. Please send an electrician today."}; fields {"service_type":true,"location":false,"preferred_time":true,"urgency":true}; error none.
- **S005 (usable_output)**: expected {"service_type":"furnace_service","location":"New Westminster","preferred_time":"Next week, weekday afternoon","urgency":"low"}; extracted {"service_type":"furnace_service","location":"New Westminster","preferred_time":"next week, any weekday afternoon","urgency":"low","summary":"Routine furnace maintenance"}; fields {"service_type":true,"location":true,"preferred_time":false,"urgency":true}; error none.
- **S007 (usable_output)**: expected {"service_type":"plumbing_service","location":"Port Moody","preferred_time":"Monday morning","urgency":"medium"}; extracted {"service_type":"plumbing_service","location":"Port Moody","preferred_time":"Monday morning","urgency":"low","summary":"Fix the bathroom tap that drips constantly"}; fields {"service_type":true,"location":true,"preferred_time":true,"urgency":false}; error none.
- **M001 (usable_output)**: expected {"service_type":"air_conditioning_service","location":null,"preferred_time":null,"urgency":"medium"}; extracted {"service_type":"air_conditioning_service","location":"unknown","preferred_time":"sometime","urgency":"medium","summary":"AC quit cooling. Could you take a look sometime?"}; fields {"service_type":true,"location":false,"preferred_time":false,"urgency":true}; error none.
- **M002 (usable_output)**: expected {"service_type":"furnace_service","location":"Maple Ridge","preferred_time":"Tomorrow morning","urgency":"high"}; extracted {"service_type":"furnace_service","location":"Maple Ridge","preferred_time":"tomorrow morning","urgency":"medium","summary":"Furnace not heating in Maple Ridge, maybe tomorrow morning"}; fields {"service_type":true,"location":true,"preferred_time":true,"urgency":false}; error none.
- **M003 (usable_output)**: expected {"service_type":"plumbing_service","location":"88 Cedar Ave, Surrey","preferred_time":null,"urgency":"high"}; extracted {"service_type":"plumbing_service","location":"88 Cedar Ave, Surrey","preferred_time":null,"urgency":"medium","summary":"Laundry room drain backing up"}; fields {"service_type":true,"location":true,"preferred_time":true,"urgency":false}; error none.
- **M004 (usable_output)**: expected {"service_type":"furnace_service","location":"Metrotown, Burnaby","preferred_time":"Tomorrow after 3","urgency":"high"}; extracted {"service_type":"furnace_service","location":"Metrotown, Burnaby","preferred_time":"after 3 tomorrow","urgency":"high","summary":"Dead furnace service request near Metrotown, Burnaby, preferred after 3 tomorrow"}; fields {"service_type":true,"location":true,"preferred_time":false,"urgency":true}; error none.
- **M005 (usable_output)**: expected {"service_type":"plumbing_service","location":"Ladner","preferred_time":null,"urgency":"medium"}; extracted {"service_type":"plumbing_service","location":"Ladner","preferred_time":"No preferred day","urgency":"low","summary":"Need a plumber for a slow bathroom sink drain in Ladder."}; fields {"service_type":true,"location":true,"preferred_time":false,"urgency":false}; error none.

## Interpretation and limitations

This is mechanical agreement with a hand-authored synthetic dataset, not production accuracy, ROI, or human validation. Labels were AI-assisted-reviewed but are not independent human ground truth. Urgency is a synthetic business convention, not clinical or professionally validated safety guidance. The v2 overlay corrects S001 and M002 to high urgency under the explicit no-heat rule; every change is documented. The v1 ledger and published v1 results are preserved unchanged.

The prose claim detector only raises a human-review flag for selected lexical cues; it cannot distinguish customer availability, negation, quotation, or provider assertions. Structured semantic scores are unaffected by this flag. Summaries always require review. Location and time grading remains conservative exact normalized equality.

## Reproduction

```bash
node scripts/ai-evaluation-v2.mjs validate
npm run test:evaluation
bash scripts/ai-evaluation-via-n8n.sh run --profile lightning --split development --run-id lightning-v2-development
bash scripts/ai-evaluation-via-n8n.sh run --profile lightning --split development --run-id lightning-v2-development --ack-circuit-reset  # only after diagnosing a transient failure
bash scripts/ai-evaluation-via-n8n.sh run --profile lightning --split held_out --run-id lightning-v2-held_out  # only after all development cases settle
node scripts/ai-evaluation-v2.mjs report --profile lightning
```

The circuit breaker opens after three consecutive timeout/provider failures. It stops new reservations; settled and uncertain case IDs are never retried. `--ack-circuit-reset` applies only to unreserved cases and should be used only after an operator diagnoses a transient service issue. Held-out calls are gated on all development cases having settled outcomes.
