# Provider recovery — 2026-09-28

## Decision

The application is not broken by the inference outage. AI enrichment is optional and the existing workflow retains its unavailable/invalid-output fallback. A separate NVIDIA Lightning profile now completes a full synthetic evaluation. This is a GO for retaining the recovery implementation and evidence, **not** a GO for unreviewed AI decisions or production deployment.

The running n8n workflows and canonical `n8n/lead-intake.json` were not changed. Activating the alternative in an integrated runtime remains a controlled end-to-end acceptance task. No push, merge, deployment, or real customer operation was performed in this recovery pass.

## Diagnosis and implementation

The configured `openai/gpt-oss-20b` requests failed to return inference responses through both native HTTPS and fetch. One 45-second diagnostic failed around 38 seconds; another reached its 45-second deadline. A minimal request also timed out at 20 seconds. Successful TLS and model-list requests establish connectivity, not inference health. The exact provider-side cause remains unknown.

Using the same credential-owning n8n container and NVIDIA endpoint, `nvidia/nemotron-3.5-lightning-30b-a3b` returned responses. A structured request with `max_tokens:512`, `reasoning_budget:0`, `stream:false`, temperature zero and JSON-object output returned schema-valid enrichment in approximately 1.68 seconds. These settings form a separately identified experiment, not a relabeled baseline. NVIDIA documents the hosted settings in its [Lightning inference API reference](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-5-lightning-30b-a3b-infer).

Implemented:

- Versioned [Lightning profile](../../n8n/evaluation/lightning-profile.json), selected explicitly with `--profile lightning`.
- Separate development and held-out ledgers; unchanged prompt, dataset, rubric, validator and 18-second deadline. No held-out tuning or selective retry.
- Profile-aware report/reproduction commands and protected-container runner support.
- Shared request accounting across baseline, candidate and diagnostics, including the original 13-call floor when historical files are absent from the protected runtime directory.
- Bounded [diagnostic tool](../../scripts/diagnose-ai-provider.mjs) with secret-free records, fsynced reservations and a shared lock/cap.
- [Opt-in workflow generator](../../scripts/export-lightning-workflow.mjs) with a regression test evaluating its generated request expression and checking model metadata/fallback preservation.

## Retained measurements

| Measurement | Development | Held out |
|---|---:|---:|
| Settled requests | 40/40 | 20/20 |
| HTTP 2xx | 39/40 | 19/20 |
| Schema-valid responses | 37/40 | 19/20 |
| Invalid responses | 2 | 0 |
| Timeouts | 1 | 1 |
| All scored fields agree / all attempts | 9/40 | 6/20 |
| All scored fields agree / usable responses | 9/37 | 6/19 |
| Uncertain ledger outcomes | 0 | 0 |

Overall: 58/60 HTTP successes, 56/60 usable responses, 15/60 strict automatic successes. **These are not production-accuracy numbers.** Exact normalized location/time comparisons can reject reasonable paraphrases; service/urgency disagreements also occur. The original prompt does not fully specify the synthetic urgency policy. Summary content always needs human review. Do not improve the score by silently changing labels or excluding failed requests.

The full [generated report](milestone-2a-results-lightning.md) validates retained outputs and recomputes grades. Raw artifacts are in [ai-evaluation-runs](ai-evaluation-runs/). Original v1 and baseline-v2 evidence is unchanged. Budget: 13 historical v1 + 6 baseline-v2 + 6 diagnostics + 60 Lightning = **85/150**, leaving 65. Diagnostic calls are not evaluation cases; missing usage/cost is unavailable, not zero. Early exploratory diagnostics preceded the final shared-lock hardening; their six calls are nevertheless retained and charged.

## Verification

- `npm run test:evaluation`: 33 tests passed, including profile equivalence and shared-budget regression.
- `./scripts/verify_phase3.sh`: 197 Python/PostgreSQL, 33 browser-helper and 48 workflow tests passed; lint, JavaScript syntax, JSON, shell, Compose, diff and tracked secret checks passed.
- The verifier used a disposable PostgreSQL container and removed it on exit. Existing runtime containers were not restarted.
- All 60 candidate calls were actual provider requests from the n8n container, not the guided-demo AI stub.
- This pass did not rerun Chrome journeys or import the generated candidate into a running workflow. Earlier browser evidence belongs to Milestone 1, not this provider evaluation.

## Reproduce and integrate safely

Offline verification/reporting (no provider calls):

```bash
npm run test:evaluation
node scripts/ai-evaluation-v2.mjs validate
node scripts/ai-evaluation-v2.mjs report --profile lightning
```

`node scripts/export-lightning-workflow.mjs` emits the opt-in workflow JSON to stdout. It deliberately preserves the baseline workflow ID: **importing it can replace that workflow**. Inspect/stage the generated artifact in an isolated instance first; retain a sanitized export of the current workflow for rollback. Do not merely change `NVIDIA_NIM_MODEL`: the tested profile also changes request settings. Existing API credentials must stay in protected runtime configuration, never in exports or evidence.

Before activation, verify runtime timeout is 18000 ms and use a synthetic lead with simulated CRM/email boundaries. Assert actual provider model/settings, persisted enrichment or fallback, one CRM identity, replay behavior, booking/confirmation boundaries and failure recovery. Leave live HighLevel/Make/customer messaging untouched unless separately authorized. If extraction quality is inadequate, retain fallback/manual review rather than advertise autonomous accuracy.
