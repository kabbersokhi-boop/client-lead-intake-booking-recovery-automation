# Milestone 2A: reproducible AI extraction evaluation

## Correction pass (2026-09-28)

**Status: partial.** The compatibility, durability, scoring-integrity, and reporting corrections are implemented and committed. The real-provider v2 baseline is resumable but incomplete: two bounded invocation segments each stopped at the explicit circuit breaker after three consecutive 18-second timeouts. Development is 6/40 settled; held-out is gated and has 0/20 requests. Do not interpret this as a completed evaluation.

Branch: `milestone-2a-ai-evaluation`

Milestone 1 baseline: `6473e37131cb9cc948b859b35dc6689e3a65d796`

Final implementation SHA: `14e8d28729f5e4c2fb2d57fd6e69a17272588c92`

Implementation commits: `11bcfb22ae7b8e04836800459e0d98f546089cdc` (protocol, harness, and retained partial run), `4af56055fcfb218c31d307282c6e4096ca88002a` (retained-output/grade consistency), `56d8c02a6be5af9c9e043b1d8db2ec9425d164a2` (fail-closed stale-lock handling), `47437ee4b4e4e3a5edadb1a3ae5a917827e23dd1` (README links), and `14e8d28729f5e4c2fb2d57fd6e69a17272588c92` (tested circuit reset and second retained invocation).

The original v1 dataset, rubric, 13 provider observations, and published v1 results remain unchanged. Their file hashes are still dataset `695e9bbc9b541ae072731f5aa7f18ff4651632168de77677855a89375594a9d9`, rubric `7c2f201908448a4624792be44870ff945833eae0551edf909defaeefd6933cf5`, 13-call ledger `238d5fdf36f43ce6771c1a55f35b2fed65b5e9b4bdcd64fd8599d73128ca2f69`, and published results `decb0fce8f2c19a5a3f449d6d78222e4bbd1fb8fbfb451d58394f1fa4d8533e2`. [The v1 results](milestone-2a-results.md) remain the historical report; they are not silently replaced by revised scores.

### Findings and corrections

1. **Experiment compatibility.** The old resume/report path compared only selected dataset/prompt fields, did not validate every row against the header, and could silently drop unknown or duplicate rows. The v2 runner uses one canonical experiment ID over provider, model, secret-free endpoint identity, inference settings, execution policy, timeout, prompt and validator hashes, effective dataset, rubric, and grader version. Resume and report use the same manifest/record validator. It rejects incompatible identities, malformed events, duplicate reservations/settlements, unknown IDs, wrong splits, mismatched input hashes, and per-record configuration drift. Manifest and record hashes are retained in each event. For usable responses, report validation also verifies the retained-output hash, reruns the exported schema validator, and recomputes grading before accepting stored scores. See [ai-evaluation-v2.mjs](../../scripts/ai-evaluation-v2.mjs) and [evaluator-v2.test.mjs](../../n8n/evaluation/evaluator-v2.test.mjs).

2. **Durable request accounting.** The v2 ledger fsyncs a request reservation before the send marker/network call, then fsyncs settlement. Any reservation without settlement becomes `unknown_request_outcome`, counts against the 150-call cap, and is never silently retried. A global exclusive lock protects cap checks and reservations. Active, foreign-host, and stale locks all fail closed; after an interrupted process, an operator must verify the runner is stopped and remove the stale lock before resuming. The protected-container wrapper now copies evidence back after a failed command and refuses divergent local/remote ledgers. Fake-transport interruption, restart/no-duplicate, concurrent lock, cap, and wrapper-failure/divergence tests pass. No n8n workflow or credentials were changed.

3. **Scoring integrity.** Audit confirmed the v1 rubric says “no heat” is high while v1 cases S001 and M002 expected medium. Those original labels and scores remain intact. The versioned [v2 dataset overlay](../../n8n/evaluation/dataset-v2-revision.json) changes only those two expected urgency labels to high, with per-case rationale. The v2 rubric also clarifies that U004’s minor contained tap drip/no damage remains medium; active leak/backup is high and uncontrolled spread is urgent. These corrections are documented in [rubric-v2.json](../../n8n/evaluation/rubric-v2.json), with the v1/v2 distinction preserved. V2 is a new frozen evaluation, not a retrospective relabeling of v1 outputs.

   The v1 prohibited-claim regex could flag customer availability, negation, and quotes as provider assertions. V2 lexical hits are human-review cues only and cannot fail otherwise-correct structured fields. Tests cover customer availability, negated and quoted text, and unsupported booking/price language. The detector does not claim semantic understanding. Every summary remains review-required. All v2 scores, if any, are mechanical agreement with synthetic labels—not validated semantic accuracy.

4. **Reproducible reporting.** V2 report generation validates the manifests and all records before deriving coverage, outcome counts, denominators, categories, field scores, and usage. Empty, partial, complete-development, malformed, and mixed-configuration artifacts are covered. Unknown reservations remain in attempted totals; missing token usage is explicitly unavailable. A populated all-pass fixture is not described as having no responses to inspect. The v1 published report was not regenerated.

5. **Circuit reset.** A resumed invocation with `--ack-circuit-reset` initially exited before sending because the open-circuit check ran before the acknowledgement was applied. The ledger stayed at three settled requests. The runner now applies acknowledgement only to an already tripped three-failure streak; it preserves shorter failure streaks. A focused offline test covers both paths. The subsequent invocation resumed at S004 and made exactly three new requests before the breaker reopened.

### Frozen v2 data and live baseline

The effective v2 dataset is 60 synthetic cases, 40 development and 20 held-out, composed from the unchanged v1 base plus the frozen two-label overlay. Its effective canonical SHA-256 is `d6780d5a945bf097cfe8dde076a30a7d6973308f7ab483234f54310e5a57b61b`; overlay SHA-256 is `fab3833ea2021e88c0ef3ed811399bf1a26d6f571b28cc9dc8b05e92a2977150`; rubric-v2 SHA-256 is `fb5e5fcc8743c7f0d0b0b73276f16a0af4132f6eeddfb9f1d55088dbc5b276cd`. Categories remain straightforward 8/0, missing/paraphrase 8/5, ambiguity/conflict 8/6, urgency policy 8/5, and unsupported/adversarial 8/4 (development/held-out). These are hand-authored synthetic cases, not customer records. The labels received bounded AI-assisted review, not independent human validation.

The actual exported production prompt and contract were used without modification: prompt hash `c95a8c1fbf4eae6ada2378d8e5ae7b23eef30f54fefccf1b3e2ceb688ba1b417`, request/validator hash `dddab8c7381379484225199bb868976ce599f0488c1cea1b8cccdbaf2dfbf5b7`. Provider is NVIDIA NIM, model `openai/gpt-oss-20b`, temperature 0, max tokens 180, reasoning effort low, JSON-object response, timeout 18,000 ms, concurrency 1, no retries. Experiment ID: `50a029bdd95e42e753fd8a3be2af17f07ebb21d4c3eeb70611a55674ea37d321`; run ID: `baseline-v2-development`.

Six v2 requests were reserved and settled in two invocation segments. Original S001–S003 timed out at 18,032, 18,005, and 18,008 ms. Resumed S004–S006 timed out at 18,021, 18,006, and 18,007 ms. Each segment stopped at its third consecutive timeout. Every attempt has a null HTTP status and unavailable token usage; availability is 0/6, schema validity and semantic correctness are unavailable (0 HTTP 2xx and 0 usable responses), and overall success is 0/6. There are 0 unknown outcomes. Cost is unavailable. Credential-free DNS/TLS diagnostics connected successfully with authorized TLS 1.3; this does not explain inference latency and is not provider availability evidence. No auth/configuration error was observed. The retained [v2 ledger](ai-evaluation-runs/baseline-v2-development.jsonl) has SHA-256 `4cbfd37213358e8d14811c000cff11f35b74fcfb935ad4aac81fc5d56340f7d0`; the [generated v2 results](milestone-2a-results-v2.md) show all denominators.

The milestone-wide count is 19 actual provider requests (the preserved 13 v1 observations plus these 6 v2 requests), with no uncertain reservations; 131 of the 150-call budget remain. The remaining 34 development cases were not sent after the breaker reopened; all 20 held-out cases remain unattempted. Held-out work must wait for every development case to have a settled outcome. A further `--ack-circuit-reset` would require new evidence of service recovery; it applies only to unreserved cases and never retries timed-out IDs. No candidate prompt was created. The deterministic guided-demo stub was not used as evidence.

### Verification and handoff

- `node scripts/ai-evaluation-v2.mjs validate` — passed; frozen v2 counts and hashes verified.
- `npm run test:evaluation` — passed, including 18 v2 evaluator tests, 2 container-wrapper synchronization tests, and the original v1 evaluator tests. No live calls were made by these tests.
- `./scripts/verify_phase3.sh` — passed: 197 backend tests (2 dependency deprecation warnings), lint, 33 browser tests, 48 workflow tests, syntax/JSON/Compose checks, and tracked-secret scan. Live runtime scenarios remain skipped by that verifier.
- `bash -n scripts/ai-evaluation-via-n8n.sh`, Node syntax checks, and `git diff --check` — passed. The guided browser demo was not rerun because application/workflow behavior did not change.

Two read-only GPT-6 Luna Medium reviewers were used. The ledger reviewer identified missing compatibility/record checks, post-request-only accounting, raceable cap logic, and unsafe wrapper synchronization; all are addressed and tested. The rubric reviewer confirmed the S001/M002 inconsistency, identified the U004 policy ambiguity and regex context failures; these are documented in the versioned v2 protocol while v1 evidence remains intact. No recursive delegation was used.

Exact commands:

```bash
node scripts/ai-evaluation-v2.mjs validate
npm run test:evaluation
bash scripts/ai-evaluation-via-n8n.sh run --split development --run-id baseline-v2-development
# Only after diagnosing a transient provider failure:
bash scripts/ai-evaluation-via-n8n.sh run --split development --run-id baseline-v2-development --ack-circuit-reset
# Held-out is valid only after all 40 development cases have settled:
bash scripts/ai-evaluation-via-n8n.sh run --split held_out --run-id baseline-v2-held_out
node scripts/ai-evaluation-v2.mjs report
./scripts/verify_phase3.sh
```

Recommendation for Milestone 2B remains an audited operator review/correction flow that preserves original output, reviewer identity/time, and versioned correction reasons, without treating extraction as booking or availability confirmation. No production accuracy, ROI, or human validation is claimed. The held-out score is not available; the current provider run is incomplete.

The remainder of this document records the original v1 delivery and result narrative as historical context.

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
