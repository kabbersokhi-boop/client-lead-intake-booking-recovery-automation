# Milestone 2A AI extraction evaluation

Status: partial live evaluation.

Dataset: synthetic-lead-extraction-v1, SHA-256 `695e9bbc9b541ae072731f5aa7f18ff4651632168de77677855a89375594a9d9` (60 cases: 40 development, 20 held out).
Rubric: synthetic-rubric-v1, SHA-256 `7c2f201908448a4624792be44870ff945833eae0551edf909defaeefd6933cf5`.
Exported system prompt SHA-256: `c95a8c1fbf4eae6ada2378d8e5ae7b23eef30f54fefccf1b3e2ceb688ba1b417`; extraction request/validator contract SHA-256: `dddab8c7381379484225199bb868976ce599f0488c1cea1b8cccdbaf2dfbf5b7`.
Model: openai/gpt-oss-20b. Provider: NVIDIA NIM OpenAI-compatible chat completions.
Run identifiers: baseline-development. Held-out run: not run.
Exported request settings: temperature=0, max_tokens=180, reasoning_effort=low, response_format=json_object, timeout=18000 ms; sequential concurrency=1.
Provider requests made: 13; retries: 0; candidate prompt: none.
Cost: unavailable (no applicable verified rate recorded).

The measured semantic score covers only exact service/urgency and conservative location/time grading plus a narrow deterministic prohibited-claim guard. Every summary requires human review and is excluded from automatic semantic-accuracy claims. Provider/schema failures remain in attempted-case denominators.

### Development baseline (selection split)

- Provider availability (HTTP 2xx / attempted): 46.2% (6/13)
- Schema valid (usable / HTTP 2xx): 100.0% (6/6)
- Automatic semantic correctness (all four auto-graded fields and no detected prohibited claim / usable): 33.3% (2/6)
- Overall success (automatic semantic successes / all attempted): 15.4% (2/13)
- Outcomes: usable 6, invalid 0, timeout 7, provider failure 0 (n=13)
- Returned token usage: 6/13 attempts; prompt 938, completion 602, total 1540. Median latency: 18007 ms across 13 attempts.
- Summary semantic review required: 6/6 usable outputs; not included in automatic semantic accuracy.

| Field | Correct among usable |
|---|---:|
| service_type | 100.0% (6/6) |
| location | 83.3% (5/6) |
| preferred_time | 100.0% (6/6) |
| urgency | 50.0% (3/6) |

| Category | Automatic semantic correct / attempted |
|---|---:|
| ambiguity_and_conflict | 0/0 |
| missing_and_paraphrase | 0/5 |
| straightforward | 2/8 |
| unsupported_and_adversarial | 0/0 |
| urgency_policy | 0/0 |

### Held-out baseline (evaluation split)

- Provider availability (HTTP 2xx / attempted): n/a (0/0)
- Schema valid (usable / HTTP 2xx): n/a (0/0)
- Automatic semantic correctness (all four auto-graded fields and no detected prohibited claim / usable): n/a (0/0)
- Overall success (automatic semantic successes / all attempted): n/a (0/0)
- Outcomes: usable 0, invalid 0, timeout 0, provider failure 0 (n=0)
- Returned token usage: 0/0 attempts; prompt 0, completion 0, total 0. Median latency: n/a across 0 attempts.
- Summary semantic review required: 0/0 usable outputs; not included in automatic semantic accuracy.

| Field | Correct among usable |
|---|---:|
| service_type | n/a (0/0) |
| location | n/a (0/0) |
| preferred_time | n/a (0/0) |
| urgency | n/a (0/0) |

| Category | Automatic semantic correct / attempted |
|---|---:|
| ambiguity_and_conflict | 0/0 |
| missing_and_paraphrase | 0/0 |
| straightforward | 0/0 |
| unsupported_and_adversarial | 0/0 |
| urgency_policy | 0/0 |

## Representative failures

- **S001 (timeout)**: Furnace, city, requested time and ordinary repair urgency are explicit; expected {"service_type":"furnace_service","location":"Surrey","preferred_time":"Tuesday afternoon","urgency":"medium"}; extracted null; field results {"service_type":false,"location":false,"preferred_time":false,"urgency":false}; safe error class `timeout`.
- **S002 (usable_output)**: Explicit AC repair, location, time and symptom; expected {"service_type":"air_conditioning_service","location":"Burnaby","preferred_time":"Friday morning","urgency":"medium"}; extracted {"service_type":"air_conditioning_service","location":"Burnaby","preferred_time":"Friday morning","urgency":"high","summary":"Repair air conditioner in Burnaby that is blowing warm air, scheduled for Friday morning."}; field results {"service_type":true,"location":true,"preferred_time":true,"urgency":false}.
- **S003 (usable_output)**: Active leak merits high in this synthetic rubric; location and time are stated; expected {"service_type":"plumbing_service","location":"Coquitlam","preferred_time":"Tomorrow after lunch","urgency":"high"}; extracted {"service_type":"plumbing_service","location":"Coquitlam","preferred_time":"Tomorrow after lunch","urgency":"medium","summary":"Leaking pipe under kitchen sink"}; field results {"service_type":true,"location":true,"preferred_time":true,"urgency":false}.
- **S004 (usable_output)**: Sparking is an immediate hazard cue; explicit city and today; expected {"service_type":"electrical_service","location":"Richmond","preferred_time":"Today","urgency":"urgent"}; extracted {"service_type":"electrical_service","location":"Richmond office","preferred_time":"today","urgency":"urgent","summary":"Outlet sparking in Richmond office, need electrician today."}; field results {"service_type":true,"location":false,"preferred_time":true,"urgency":true}.
- **S005 (timeout)**: Routine maintenance and flexible next-week timing; expected {"service_type":"furnace_service","location":"New Westminster","preferred_time":"Next week, weekday afternoon","urgency":"low"}; extracted null; field results {"service_type":false,"location":false,"preferred_time":false,"urgency":false}; safe error class `timeout`.
- **S007 (timeout)**: Plumbing repair; routine drip is medium by policy; expected {"service_type":"plumbing_service","location":"Port Moody","preferred_time":"Monday morning","urgency":"medium"}; extracted null; field results {"service_type":false,"location":false,"preferred_time":false,"urgency":false}; safe error class `timeout`.
- **M001 (usable_output)**: Common paraphrase; neither location nor a concrete time is supplied; expected {"service_type":"air_conditioning_service","location":null,"preferred_time":null,"urgency":"medium"}; extracted {"service_type":"air_conditioning_service","location":null,"preferred_time":null,"urgency":"high","summary":"AC not cooling, request inspection."}; field results {"service_type":true,"location":true,"preferred_time":true,"urgency":false}.
- **M002 (timeout)**: Typos do not change explicit furnace, city or tomorrow morning; expected {"service_type":"furnace_service","location":"Maple Ridge","preferred_time":"Tomorrow morning","urgency":"medium"}; extracted null; field results {"service_type":false,"location":false,"preferred_time":false,"urgency":false}; safe error class `timeout`.

## Dataset and label limitations

All examples are hand-authored synthetic enquiries. Labels encode the explicit v1 rubric and are not independent human ground truth; there was an independent AI-assisted rubric review, not a human validation study. The urgency convention is only for repeatable portfolio evaluation and is not a clinical or professionally validated safety policy. Location/time normalization intentionally avoids guessing aliases, relative dates, or time zones.

Scoring caveat from development case S004: the input explicitly says “Richmond office,” while the canonical location label is “Richmond.” The extracted location preserves that source-supported specificity, but the conservative exact normalized matcher marks it incorrect. The label was not changed after evaluation; this is a known automatic-scoring false-negative risk and needs operator review.

Category counts (development / held out): ambiguity_and_conflict 8/6; missing_and_paraphrase 8/5; straightforward 8/0; unsupported_and_adversarial 8/4; urgency_policy 8/5.

## Limitations and next step

No candidate prompt was created or selected: only 13/40 development cases were attempted and just 6 usable outputs remain, which is too little evidence to distinguish a repeatable prompt defect from sampling noise. The 20 held-out cases were not sent.

No production accuracy, customer ROI, or human validation is claimed. The narrow automatic claim guard can miss unsupported prose; the review-marked summaries must be checked by an operator. Milestone 2B should add an audited operator review/correction workflow that captures original model output, accepted corrections, reviewer identity/time, and a versioned reason without allowing model output to confirm bookings or invent facts.

Reproduction commands: `node scripts/ai-evaluation.mjs validate`; `npm run test:evaluation`; `bash scripts/ai-evaluation-via-n8n.sh run --split development --run-id baseline-development`; after development selection, `bash scripts/ai-evaluation-via-n8n.sh run --split held_out --run-id baseline-held-out`; then `node scripts/ai-evaluation.mjs report`.
