# Milestone 2A: reproducible AI extraction evaluation

## Status

**Partial.** The offline evaluator, frozen synthetic dataset, rubric, CI checks, and report are complete. The real NVIDIA baseline is incomplete because repeated requests exceeded the workflow's 18-second timeout. Thirteen development cases were attempted; the remaining 27 development cases and all 20 held-out cases were not sent. Held-out data was not used for tuning.

Branch: `milestone-2a-ai-evaluation`

Baseline: `6473e37131cb9cc948b859b35dc6689e3a65d796`

Implementation: `4cf17483f729b9a75a62dc5ef6dcc5163774a3b0`

## Changes

- Added a versioned, 60-case synthetic dataset and urgency/service rubric. It contains 40 development and 20 held-out cases. All five extraction fields are represented; summaries use per-case `review` grading and are excluded from automatic semantic accuracy.
- Added an offline evaluator that reads the actual system prompt, request settings, and validation JavaScript from the exported n8n workflow. It invokes the exported validator in a time-limited Node VM with narrow synthetic inputs; it does not evaluate n8n expressions or change production workflow behavior.
- Added deterministic field grading, a narrow unsupported-price/booking/availability claim guard, denominators for failures, version/hash compatibility checks, resumable per-case ledgers, safe request/output evidence, report regeneration, and an offline test suite in CI.
- Added a runner that stages only the evaluator, exported workflow, dataset, and rubric in the existing n8n runtime. The NVIDIA key remains in that container; the persistent ledger is written to its existing n8n data volume. No provider credentials are copied into the repository.
- Linked this report from the README. No booking, CRM, recovery, email, deployment, or production prompt behavior changed.

## Dataset and grading

The cases are hand-authored synthetic HVAC/home-service enquiries. No customer records or production examples were read. There are five categories, with development/held-out counts: straightforward 8/0; missing and paraphrase 8/5; ambiguity and conflict 8/6; urgency policy 8/5; unsupported and adversarial 8/4.

Dataset SHA-256: `695e9bbc9b541ae072731f5aa7f18ff4651632168de77677855a89375594a9d9`

Rubric SHA-256: `7c2f201908448a4624792be44870ff945833eae0551edf909defaeefd6933cf5`

Exported system prompt SHA-256: `c95a8c1fbf4eae6ada2378d8e5ae7b23eef30f54fefccf1b3e2ceb688ba1b417`

Request/validator contract SHA-256: `dddab8c7381379484225199bb868976ce599f0488c1cea1b8cccdbaf2dfbf5b7`

Urgency, service-boundary, and relative-time labels are conventions for reproducible synthetic scoring. They are not clinical or professionally validated safety guidance. Service and urgency use exact enum equality. Location and time use conservative case/whitespace normalization; the grader does not infer aliases, dates, or time zones. The summary rationale is review guidance, not an exact-string target. The rubric and category counts are in [rubric-v1.json](../../n8n/evaluation/rubric-v1.json) and [dataset-v1.json](../../n8n/evaluation/dataset-v1.json).

## Real-provider run

Provider: NVIDIA NIM OpenAI-compatible chat completions

Model: `openai/gpt-oss-20b`

Run ID: `baseline-development`

Settings: temperature 0, max tokens 180, reasoning effort `low`, JSON-object response format, 18,000 ms timeout, sequential concurrency 1, zero retries.
Provider requests: 13, each for a unique development case. Returned usage was prompt 938, completion 602, total 1,540 tokens across six responses; seven timeouts returned no usage. Median latency across the 13 attempts was 18,007 ms. Cost is unavailable because no applicable verified rate was recorded.

| Measure | Result |
|---|---:|
| Provider availability (HTTP 2xx / attempted) | 46.2% (6/13) |
| Schema validity (usable / HTTP 2xx) | 100.0% (6/6) |
| Automatic semantic correctness (all four automatic fields / usable) | 33.3% (2/6) |
| Overall success (automatic semantic successes / all attempts) | 15.4% (2/13) |
| Outcomes | 6 usable, 0 invalid, 7 timeout, 0 provider failure (n=13) |

Automatic field results among usable outputs: service type 6/6, location 5/6, preferred time 6/6, and urgency 3/6. Every usable summary still requires human review; no summary semantic-accuracy claim is made. The report retains failure records in overall denominators. Category results and the full case-level ledger are in [milestone-2a-results.md](milestone-2a-results.md) and [baseline-development.jsonl](ai-evaluation-runs/baseline-development.jsonl).

Representative errors include over-labeling ordinary same-day AC work as `high` (S002), under-labeling an active leak as `medium` rather than the rubric's `high` (S003), and labeling an unspecified-time AC request `high` (M001). Case S004 returned `Richmond office` where the frozen canonical location is `Richmond`; the input supports that extra specificity, but the conservative matcher counts it as wrong. This is an acknowledged scoring false negative; the label was not edited after evaluation.

DNS and TLS to the configured NVIDIA endpoint succeeded. The repeated failures were request timeouts at the actual 18-second workflow limit, with no HTTP status; they did not indicate an authorization error. The first timeout stopped that invocation; resume skipped completed case IDs and continued with new ones. After 13 attempts and seven timeouts, evaluation was left partial. No candidate prompt was created because only six usable development outputs were available, too few to select a prompt change reliably. Held-out requests: zero.

This is evidence about one bounded synthetic run, not production accuracy, customer ROI, or human-validated performance. AI-assisted labels are not independent human ground truth. The deterministic claim guard cannot reliably identify every unsupported prose claim; operator review is needed for summaries and ambiguous location specificity.

## Verification

- `node scripts/ai-evaluation.mjs validate` — passed; 60 cases, 40/20 split, and hashes recorded above.
- `npm run test:evaluation` — passed; negative checks cover schema-valid semantic errors, invented nullable fields, prohibited price claims, missing output, timeout/malformed totals, changing expectations/output, resume selection, version incompatibility, and adversarial text isolation.
- `./scripts/verify_phase3.sh` — passed: 197 backend tests, Python lint, browser suite, 48 workflow tests, syntax/JSON/Compose checks, and tracked secret scan. The script's live n8n/NVIDIA/Mailpit scenarios remain its documented skip.
- `node --check scripts/ai-evaluation.mjs`, `bash -n scripts/ai-evaluation-via-n8n.sh`, and `git diff --check` — passed.
- The guided browser demo was not rerun because no runtime workflow or application code changed. The provider evaluation used only synthetic cases.
- The protected-container runner's shell syntax was checked. The sandbox prevented Docker calls nested inside that shell wrapper, so its equivalent direct `docker cp`/`docker exec` sequence was used for the actual run. It staged no credential files and printed no secrets.

## Files and design references

- [ai-evaluation.mjs](../../scripts/ai-evaluation.mjs): exported contract extraction, exact validator execution, scoring, ledger, hashes, call cap, and report generation.
- [ai-evaluation-via-n8n.sh](../../scripts/ai-evaluation-via-n8n.sh): keeps runtime credentials in n8n and synchronizes the run ledger.
- [evaluator.test.mjs](../../n8n/evaluation/evaluator.test.mjs): deterministic negative and resume/version tests.
- [CI workflow](../../.github/workflows/ci.yml) and [README](../../README.md): offline check integration and report link.

## Subagent review and risks

Two read-only GPT-6 Luna Medium reviewers were used, with no recursive delegation. The contract inventory confirmed the exact five fields, enums, 160/600-character limits, 180-token/18-second request controls, and fallback behavior. It also noted that the backend cleans whitespace-only optional text to null while the exported n8n validator rejects it; evaluation follows the exported validator, which is the requested extraction contract. The rubric reviewer called out urgency cues, multiple services, `unknown` versus general service, relative time, and stale hazards. Those boundaries are written into the rubric, and the location false-negative risk found in the live sample is reported rather than relabeled.

Unresolved risks are the incomplete, timeout-heavy provider sample; untested held-out behavior; unreviewed summaries; synthetic/AI-assisted labels; and deterministic grader false positives/negatives for source-supported paraphrases. No additional provider was tried or added, and no paid infrastructure was provisioned.

## Reproduction

From the repository root:

```bash
node scripts/ai-evaluation.mjs validate
npm run test:evaluation
bash scripts/ai-evaluation-via-n8n.sh run --split development --run-id baseline-development
bash scripts/ai-evaluation-via-n8n.sh run --split held_out --run-id baseline-held-out
node scripts/ai-evaluation.mjs report
```

The runner resumes from the persistent ledger and refuses held-out calls until all 40 development case IDs are recorded. The held-out command above is for a future complete development run; it was not run for this report. The helper copies only synthetic artifacts and source files; it does not copy credential values.

## Milestone 2B recommendation

Build an audited operator review/correction workflow. Show the original enquiry and extraction, require an operator to confirm or correct uncertain fields and summaries, retain reviewer identity/time and a versioned reason, and preserve the original model response alongside corrections. Corrections should remain auditable evaluation evidence and must not imply booking confirmation or guaranteed availability.
