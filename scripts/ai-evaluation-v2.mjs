#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readContract, runExportedValidator } from './ai-evaluation.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DATASET_V1 = path.join(ROOT, 'n8n/evaluation/dataset-v1.json');
const DATASET_REVISION = path.join(ROOT, 'n8n/evaluation/dataset-v2-revision.json');
const RUBRIC = path.join(ROOT, 'n8n/evaluation/rubric-v2.json');
const RUN_DIR = process.env.AI_EVAL_RUN_DIR ? path.resolve(process.env.AI_EVAL_RUN_DIR) : path.join(ROOT, 'docs/reviews/ai-evaluation-runs');
const CASES = ['service_type', 'location', 'preferred_time', 'urgency'];
const OUTCOMES = ['usable_output', 'invalid_output', 'timeout', 'provider_failure'];
const sha256 = (s) => crypto.createHash('sha256').update(s).digest('hex');
const read = (p) => fs.readFileSync(p, 'utf8');
const norm = (value) => typeof value === 'string' ? value.trim().toLocaleLowerCase('en').replace(/\s+/g, ' ') : value;

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(',')}}`;
  return JSON.stringify(value);
}

function loadDataset() {
  const baseText = read(DATASET_V1);
  const base = JSON.parse(baseText);
  const revisionText = read(DATASET_REVISION);
  const revision = JSON.parse(revisionText);
  if (sha256(baseText) !== revision.base_sha256) throw new Error('Dataset v2 overlay base hash mismatch.');
  const dataset = structuredClone(base);
  dataset.version = 'synthetic-hvac-v2';
  for (const [id, override] of Object.entries(revision.case_overrides)) {
    const item = dataset.cases.find((candidate) => candidate.id === id);
    if (!item || !override.expected || !override.rationale) throw new Error(`Invalid dataset revision for ${id}.`);
    item.expected = override.expected;
    item.rationale = override.rationale;
  }
  const canonical = stableJson({ base_sha256: revision.base_sha256, revision, dataset });
  return { dataset, revision, revisionText, datasetHash: sha256(canonical), datasetCanonical: canonical };
}

function endpointIdentity(url) {
  const parsed = new URL(url);
  if (parsed.protocol !== 'https:') throw new Error('Provider endpoint must use HTTPS.');
  const knownNvidiaPath = parsed.hostname === 'integrate.api.nvidia.com' && parsed.pathname === '/v1/chat/completions';
  const pathIdentity = knownNvidiaPath ? parsed.pathname : `/path-sha256/${sha256(parsed.pathname)}`;
  return `${parsed.origin}${pathIdentity}`;
}

function makeManifest({ provider, model, endpoint, settings, executionPolicy = { concurrency: 1, retries: 0, failure_circuit_breaker: '3-consecutive-timeout-or-provider-failures' }, timeoutMs, datasetHash, rubricHash, contract }) {
  const endpointId = /^https:\/\/[^/?#]+\/path-sha256\/[a-f0-9]{64}$/.test(endpoint) ? endpoint : endpointIdentity(endpoint);
  const identity = {
    provider,
    model,
    endpoint_identity: endpointId,
    inference_settings: settings,
    execution_policy: executionPolicy,
    timeout_ms: timeoutMs,
    prompt_hash: contract.promptHash,
    validator_contract_hash: contract.contractHash,
    dataset_hash: datasetHash,
    rubric_hash: rubricHash,
    grader_version: 'milestone-2a-grader-v2'
  };
  return { ...identity, experiment_id: sha256(stableJson(identity)) };
}

function manifestHash(manifest) {
  const { experiment_id, ...identity } = manifest;
  if (sha256(stableJson(identity)) !== experiment_id) throw new Error('Experiment manifest identity hash is invalid.');
  return sha256(stableJson(manifest));
}

function eventContext(manifest, runId, split, item) {
  return {
    experiment_id: manifest.experiment_id,
    manifest_hash: manifestHash(manifest),
    provider: manifest.provider,
    model: manifest.model,
    endpoint_identity: manifest.endpoint_identity,
    inference_settings: manifest.inference_settings,
    execution_policy: manifest.execution_policy,
    timeout_ms: manifest.timeout_ms,
    prompt_hash: manifest.prompt_hash,
    validator_contract_hash: manifest.validator_contract_hash,
    dataset_hash: manifest.dataset_hash,
    rubric_hash: manifest.rubric_hash,
    grader_version: manifest.grader_version,
    run_id: runId,
    split,
    case_id: item.id,
    input_hash: sha256(item.input)
  };
}

function expectedMatches(actual, expected, field) {
  const options = Array.isArray(expected) ? expected : [expected];
  return options.some((wanted) => field === 'location' || field === 'preferred_time' ? norm(actual) === norm(wanted) : actual === wanted);
}

// Lexical hits are review cues only: context, quotation, and speaker are not interpreted.
const proseReviewSignal = /(?:\$\s*\d|\b(?:confirmed|booked)\s+(?:for|at|on)\b|\b(?:guaranteed|available)\s+(?:today|tomorrow|at\s+\d|on\s+\w+))/i;

function gradeCase(item, payload) {
  const extracted = payload?.enrichment ?? null;
  const fieldResults = Object.fromEntries(CASES.map((field) => [field, extracted !== null && expectedMatches(extracted[field], item.expected[field], field)]));
  const urgencyReviewRequired = false;
  const automaticFields = urgencyReviewRequired ? CASES.filter((field) => field !== 'urgency') : CASES;
  const prose = typeof extracted?.summary === 'string' ? extracted.summary : '';
  const proseReview = proseReviewSignal.test(prose);
  const automaticSemanticCorrect = extracted !== null && automaticFields.every((field) => fieldResults[field]);
  return {
    field_results: fieldResults,
    automatic_fields: automaticFields,
    automatic_semantic_correct: automaticSemanticCorrect,
    urgency_review_required: urgencyReviewRequired,
    prose_claim_review_required: proseReview,
    summary_review_required: true
  };
}

function validatePayload(response, contract, input) {
  try { return runExportedValidator(contract, response, input); }
  catch { return { enrichment: null, ai_status: 'fallback_invalid' }; }
}

function appendDurable(file, row) {
  const fd = fs.openSync(file, 'a', 0o600);
  try { fs.writeSync(fd, `${JSON.stringify(row)}\n`); fs.fsyncSync(fd); }
  finally { fs.closeSync(fd); }
}

function acquireLock(lockPath, { pidIsAlive = (pid) => { try { process.kill(pid, 0); return true; } catch (e) { return e.code !== 'ESRCH'; } } } = {}) {
  fs.mkdirSync(path.dirname(lockPath), { recursive: true });
  const lockData = { pid: process.pid, hostname: os.hostname(), started_at: new Date().toISOString(), token: crypto.randomUUID() };
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const fd = fs.openSync(lockPath, 'wx', 0o600);
      fs.writeSync(fd, `${JSON.stringify(lockData)}\n`);
      fs.fsyncSync(fd);
      fs.closeSync(fd);
      return () => {
        try {
          const current = JSON.parse(read(lockPath));
          if (current.token === lockData.token) fs.unlinkSync(lockPath);
        } catch (error) { if (error.code !== 'ENOENT') throw error; }
      };
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      let current;
      try { current = JSON.parse(read(lockPath)); }
      catch { throw new Error('Evaluation lock is unreadable; refusing concurrent calls. Inspect and recover manually.'); }
      const active = current.hostname === os.hostname() && pidIsAlive(current.pid);
      if (active) throw new Error(`Evaluation already running under PID ${current.pid}; refusing concurrent invocation.`);
      fs.unlinkSync(lockPath);
    }
  }
  throw new Error('Unable to acquire evaluation lock.');
}

function parseAndValidateLedger({ text, dataset, expectedManifest = null, expectedSplit = null, expectedRunId = null }) {
  if (!text.trim()) throw new Error('Ledger is empty.');
  const lines = text.split(/\r?\n/).filter(Boolean);
  const rows = lines.map((line, index) => {
    try { return JSON.parse(line); } catch { throw new Error(`Malformed ledger JSON at line ${index + 1}.`); }
  });
  const header = rows[0];
  if (header.kind !== 'header' || !header.manifest) throw new Error('Ledger header or manifest is missing.');
  const manifest = header.manifest;
  manifestHash(manifest);
  if (header.manifest_hash !== manifestHash(manifest)) throw new Error('Ledger header manifest hash mismatch.');
  if (expectedManifest && header.manifest_hash !== manifestHash(expectedManifest)) throw new Error('Ledger experiment is incompatible with current manifest.');
  if (expectedSplit && header.split !== expectedSplit) throw new Error('Ledger split mismatch.');
  if (expectedRunId && header.run_id !== expectedRunId) throw new Error('Ledger run ID mismatch.');
  if (header.split !== 'development' && header.split !== 'held_out') throw new Error('Ledger has an invalid split.');
  if (header.run_id !== `baseline-v2-${header.split}`) throw new Error('Ledger run ID does not match split.');
  if (manifest.dataset_hash !== dataset.datasetHash) throw new Error('Ledger dataset does not match frozen dataset v2.');
  const caseMap = new Map(dataset.dataset.cases.map((item) => [item.id, item]));
  const reservations = new Map();
  const byCase = new Map();
  const sent = new Set();
  const settlements = new Map();
  for (const event of rows.slice(1)) {
    if (!['reservation', 'sent', 'settlement'].includes(event.kind)) throw new Error(`Unknown ledger event kind: ${event.kind}`);
    const item = caseMap.get(event.case_id);
    if (!item) throw new Error(`Unknown case ID ${event.case_id}.`);
    if (item.split !== header.split || event.split !== header.split) throw new Error(`Wrong split for case ${event.case_id}.`);
    if (event.run_id !== header.run_id) throw new Error(`Wrong run ID for case ${event.case_id}.`);
    const expectedContext = eventContext(manifest, header.run_id, header.split, item);
    for (const [key, value] of Object.entries(expectedContext)) {
      if (stableJson(event[key]) !== stableJson(value)) throw new Error(`Record ${event.case_id} is inconsistent with manifest/case on ${key}.`);
    }
    const reservation = reservations.get(event.request_id);
    if (event.kind === 'reservation') {
      if (reservation) throw new Error(`Duplicate request reservation ${event.request_id}.`);
      if (byCase.has(event.case_id)) throw new Error(`Duplicate case reservation ${event.case_id}.`);
      if (!event.request_id || typeof event.request_id !== 'string') throw new Error('Reservation has no request ID.');
      reservations.set(event.request_id, event);
      byCase.set(event.case_id, event.request_id);
    } else {
      if (!reservation) throw new Error(`Event ${event.kind} has no reservation.`);
      if (reservation.case_id !== event.case_id) throw new Error('Request event changed case ID.');
      if (event.kind === 'sent') {
        if (sent.has(event.request_id) || settlements.has(event.request_id)) throw new Error('Duplicate sent event.');
        sent.add(event.request_id);
      } else {
        if (!sent.has(event.request_id)) throw new Error('Settlement without durable sent marker.');
        if (settlements.has(event.request_id)) throw new Error('Duplicate settlement.');
        if (!OUTCOMES.includes(event.outcome)) throw new Error(`Invalid settled outcome ${event.outcome}.`);
        if (event.latency_ms !== null && (!Number.isFinite(event.latency_ms) || event.latency_ms < 0)) throw new Error('Invalid settlement latency.');
        if (event.http_status !== null && (!Number.isInteger(event.http_status) || event.http_status < 100 || event.http_status > 599)) throw new Error('Invalid HTTP status.');
        if (event.outcome === 'usable_output' && (!(event.http_status >= 200 && event.http_status < 300) || !event.extracted || !event.grading || typeof event.grading.automatic_semantic_correct !== 'boolean')) throw new Error('Usable settlement has inconsistent status or missing extraction/grading.');
        if ((event.outcome === 'timeout' || event.outcome === 'provider_failure') && event.grading !== null) throw new Error('Failed request cannot have semantic grading.');
        if (event.token_usage !== null && event.token_usage !== undefined && typeof event.token_usage !== 'object') throw new Error('Malformed token usage.');
        settlements.set(event.request_id, event);
      }
    }
  }
  const attempts = [...reservations.values()].map((reservation) => ({
    reservation,
    sent: sent.has(reservation.request_id),
    settlement: settlements.get(reservation.request_id) ?? null,
    outcome: settlements.get(reservation.request_id)?.outcome ?? 'unknown_request_outcome'
  }));
  return { header, manifest, attempts, reservations, settlements, caseMap };
}

function deriveStats(validated) {
  const attempts = validated.attempts;
  const settled = attempts.filter((a) => a.settlement).map((a) => a.settlement);
  const usable = settled.filter((r) => r.outcome === 'usable_output');
  const http2xx = settled.filter((r) => Number.isInteger(r.http_status) && r.http_status >= 200 && r.http_status < 300);
  const automatic = usable.filter((r) => r.grading.automatic_semantic_correct);
  const fields = Object.fromEntries(CASES.map((field) => {
    const scored = usable.filter((r) => r.grading.automatic_fields.includes(field));
    const correct = scored.filter((r) => r.grading.field_results[field]).length;
    return [field, { correct, denominator: scored.length, percent: scored.length ? 100 * correct / scored.length : null }];
  }));
  const categoryStats = {};
  for (const category of new Set([...validated.caseMap.values()].filter((i) => i.split === validated.header.split).map((i) => i.category))) {
    const ids = new Set([...validated.caseMap.values()].filter((i) => i.split === validated.header.split && i.category === category).map((i) => i.id));
    const rows = attempts.filter((a) => ids.has(a.reservation.case_id));
    const good = rows.filter((a) => a.settlement?.grading?.automatic_semantic_correct).length;
    categoryStats[category] = { attempted: rows.length, cases_in_split: ids.size, automatic_successes: good };
  }
  const outcomes = Object.fromEntries([...OUTCOMES, 'unknown_request_outcome'].map((outcome) => [outcome, attempts.filter((a) => a.outcome === outcome).length]));
  const usageRecords = settled.filter((r) => r.token_usage && typeof r.token_usage === 'object');
  const sumUsage = (field) => {
    const values = usageRecords.map((r) => r.token_usage[field]).filter(Number.isFinite);
    return { total: values.reduce((sum, value) => sum + value, 0), responses_with_value: values.length };
  };
  return {
    attempted: attempts.length,
    provider_available: http2xx.length,
    schema_valid: usable.length,
    semantic_correct: automatic.length,
    overall_success: automatic.length,
    outcomes,
    fields,
    categories: categoryStats,
    usage: {
      responses_with_usage: usageRecords.length,
      prompt_tokens: sumUsage('prompt_tokens'),
      completion_tokens: sumUsage('completion_tokens'),
      total_tokens: sumUsage('total_tokens')
    },
    latency_ms: settled.map((r) => r.latency_ms).filter(Number.isFinite)
  };
}

function percent(n, d) { return d ? `${(100 * n / d).toFixed(1)}% (${n}/${d})` : `n/a (0/${d})`; }

function pendingCases(cases, attempts) {
  const reserved = new Set(attempts.map((attempt) => attempt.reservation.case_id));
  return cases.filter((item) => !reserved.has(item.id));
}

function assertRequestBudget(used, cap = 150) {
  if (!Number.isSafeInteger(used) || used < 0 || used >= cap) throw new Error(`Global milestone provider-request budget of ${cap} reservations is exhausted.`);
}

async function budgetedAttempt({ used, cap = 150, ...attempt }) {
  assertRequestBudget(used, cap);
  return oneAttempt(attempt);
}

function runReportSection(split, validated) {
  const stats = deriveStats(validated);
  const caseCount = [...validated.caseMap.values()].filter((item) => item.split === split).length;
  const statuses = Object.entries(stats.outcomes).map(([name, count]) => `${name} ${count}`).join(', ');
  const usageValue = (value) => value.responses_with_value ? `${value.total} across ${value.responses_with_value}` : 'unavailable (0 returned)';
  const lines = [
    `### ${split} (${stats.attempted}/${caseCount} reservations)`, '',
    `- Provider availability (2xx / all reserved attempts): ${percent(stats.provider_available, stats.attempted)}`,
    `- Schema-valid usable outputs (usable / 2xx): ${percent(stats.schema_valid, stats.provider_available)}`,
    `- Automatic semantic agreement (correct / usable): ${percent(stats.semantic_correct, stats.schema_valid)}`,
    `- Overall success (correct / all reserved attempts): ${percent(stats.overall_success, stats.attempted)}`,
    `- Outcomes: ${statuses}`,
    `- Token usage: returned on ${stats.usage.responses_with_usage}/${stats.attempted} attempts; prompt ${usageValue(stats.usage.prompt_tokens)}, completion ${usageValue(stats.usage.completion_tokens)}, total ${usageValue(stats.usage.total_tokens)}; missing usage is unavailable, not zero per response. Cost unavailable unless a verified applicable rate is supplied.`,
    `- Summary review required for ${stats.schema_valid}/${stats.schema_valid} usable outputs. Prose lexical signals are review cues only and do not affect structured-field accuracy.`, '',
    '| Field | Correct / automatically scored usable outputs |', '|---|---:|',
    ...Object.entries(stats.fields).map(([field, s]) => `| ${field} | ${percent(s.correct, s.denominator)} |`), '',
    '| Category | Automatic successes / attempted (cases in split) |', '|---|---:|',
    ...Object.entries(stats.categories).map(([category, s]) => `| ${category} | ${s.automatic_successes}/${s.attempted} (${s.cases_in_split} cases) |`), ''
  ];
  return lines.join('\n');
}

function formatReport(validatedRuns, datasetInfo) {
  const reports = [];
  const first = validatedRuns[0]?.manifest;
  if (validatedRuns.some((run) => run.manifest.experiment_id !== first?.experiment_id)) throw new Error('Cannot report mixed experiment configurations.');
  const totalDatasetCases = datasetInfo.dataset.cases.length;
  const splitCounts = Object.fromEntries(['development', 'held_out'].map((split) => [split, datasetInfo.dataset.cases.filter((c) => c.split === split).length]));
  const rows = validatedRuns.flatMap((run) => run.attempts.map((a) => a.settlement).filter(Boolean));
  const failures = rows.filter((record) => record.outcome !== 'usable_output' || !record.grading.automatic_semantic_correct);
  const coverage = Object.fromEntries(['development', 'held_out'].map((split) => {
    const expected = splitCounts[split];
    const run = validatedRuns.find((candidate) => candidate.header.split === split);
    const reserved = run?.attempts.length ?? 0;
    const settled = run?.attempts.filter((attempt) => attempt.settlement).length ?? 0;
    return [split, { expected, reserved, settled, complete: reserved === expected && settled === expected }];
  }));
  const runStatus = !validatedRuns.length ? 'no retained run ledger' : Object.values(coverage).every((value) => value.complete) ? 'complete across both frozen splits' : 'partial or not started across frozen splits';
  reports.push('# Milestone 2A real-provider evaluation — protocol v2', '');
  reports.push(`- Coverage status: ${runStatus}; ${Object.entries(coverage).map(([split, value]) => `${split} ${value.reserved}/${value.expected} reserved, ${value.settled}/${value.expected} settled`).join('; ')}.`);
  reports.push(`- Dataset: ${datasetInfo.dataset.version}, ${totalDatasetCases} synthetic cases (${splitCounts.development} development / ${splitCounts.held_out} held out), effective dataset hash \`${datasetInfo.datasetHash}\`.`);
  reports.push(`- Dataset revision SHA-256: \`${sha256(datasetInfo.revisionText)}\`; rubric: ${JSON.parse(read(RUBRIC)).version}, SHA-256 \`${sha256(read(RUBRIC))}\`.`);
  reports.push(`- Experiment ID: \`${first?.experiment_id ?? 'none'}\`; provider: ${first?.provider ?? 'not configured'}; model: ${first?.model ?? 'not run'}; endpoint identity: ${first?.endpoint_identity ?? 'not run'}.`);
  reports.push(`- Prompt SHA-256: \`${first?.prompt_hash ?? 'unavailable'}\`; exported validator/request contract SHA-256: \`${first?.validator_contract_hash ?? 'unavailable'}\`; grader: ${first?.grader_version ?? 'milestone-2a-grader-v2'}.`);
  reports.push(`- Effective request settings: \`${stableJson(first?.inference_settings ?? {})}\`; execution policy: \`${stableJson(first?.execution_policy ?? {})}\`; timeout: ${first?.timeout_ms ?? 'unavailable'} ms.`);
  reports.push(`- Attempts: ${validatedRuns.reduce((n, r) => n + r.attempts.length, 0)}; known legacy v1 provider observations are separate historical requests. Cost unavailable without a verified applicable rate.`, '');
  for (const validated of validatedRuns) reports.push(runReportSection(validated.header.split, validated));
  reports.push('## Representative failures', '');
  if (!failures.length && rows.length) reports.push(`No settled failures among ${rows.length} retained responses; this does not make the synthetic labels human-validated. Inspect all retained synthetic outputs and review-required summaries.`, '');
  else if (!failures.length) reports.push('No settled provider responses are retained yet. Unknown reservations are reported separately and are not treated as responses.', '');
  else for (const record of failures.slice(0, 10)) {
    const item = datasetInfo.dataset.cases.find((candidate) => candidate.id === record.case_id);
    reports.push(`- **${record.case_id} (${record.outcome})**: expected ${JSON.stringify(item?.expected)}; extracted ${JSON.stringify(record.extracted)}; fields ${JSON.stringify(record.grading?.field_results ?? {})}; error ${record.error_class ?? 'none'}.`);
  }
  reports.push('', '## Interpretation and limitations', '',
    'This is mechanical agreement with a hand-authored synthetic dataset, not production accuracy, ROI, or human validation. Labels were AI-assisted-reviewed but are not independent human ground truth. Urgency is a synthetic business convention, not clinical or professionally validated safety guidance. The v2 overlay corrects S001 and M002 to high urgency under the explicit no-heat rule; every change is documented. The v1 ledger and published v1 results are preserved unchanged.', '',
    'The prose claim detector only raises a human-review flag for selected lexical cues; it cannot distinguish customer availability, negation, quotation, or provider assertions. Structured semantic scores are unaffected by this flag. Summaries always require review. Location and time grading remains conservative exact normalized equality.', '',
    '## Reproduction', '',
    '```bash',
    'node scripts/ai-evaluation-v2.mjs validate',
    'npm run test:evaluation',
    'bash scripts/ai-evaluation-via-n8n.sh run --split development --run-id baseline-v2-development',
    'bash scripts/ai-evaluation-via-n8n.sh run --split development --run-id baseline-v2-development --ack-circuit-reset  # only after diagnosing a transient failure',
    'bash scripts/ai-evaluation-via-n8n.sh run --split held_out --run-id baseline-v2-held_out  # only after all development cases settle',
    'node scripts/ai-evaluation-v2.mjs report',
    '```', '',
    'The circuit breaker opens after three consecutive timeout/provider failures. It stops new reservations; settled and uncertain case IDs are never retried. `--ack-circuit-reset` applies only to unreserved cases and should be used only after an operator diagnoses a transient service issue. Held-out calls are gated on all development cases having settled outcomes.', '');
  return reports.join('\n');
}

function validateRecordsForReport(datasetInfo, runIds) {
  const validated = [];
  const contract = readContract();
  const rubricHash = sha256(read(RUBRIC));
  for (const runId of runIds) {
    const file = path.join(RUN_DIR, `${runId}.jsonl`);
    if (!fs.existsSync(file)) continue;
    const text = read(file);
    const first = JSON.parse(text.split(/\r?\n/, 1)[0]);
    const recorded = first.manifest;
    const expectedManifest = makeManifest({
      provider: recorded?.provider,
      model: recorded?.model,
      endpoint: recorded?.endpoint_identity,
      settings: recorded?.inference_settings,
      executionPolicy: recorded?.execution_policy,
      executionPolicy: recorded?.execution_policy,
      timeoutMs: recorded?.timeout_ms,
      datasetHash: datasetInfo.datasetHash,
      rubricHash,
      contract
    });
    validated.push(parseAndValidateLedger({ text, dataset: datasetInfo, expectedManifest, expectedRunId: runId }));
  }
  if (validated.length > 1 && new Set(validated.map((run) => run.manifest.experiment_id)).size !== 1) throw new Error('Run report rejected mixed experiment configurations.');
  return validated;
}

function loadApiConfig(contract) {
  const env = { ...process.env };
  const envFile = path.join(ROOT, '.env');
  if (fs.existsSync(envFile)) for (const line of read(envFile).split(/\r?\n/)) {
    const match = line.match(/^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/);
    if (match && !env[match[1]]) env[match[1]] = match[2].replace(/^(["'])(.*)\1$/, '$2');
  }
  const key = env.NVIDIA_NIM_API_KEY;
  const model = env.NVIDIA_NIM_MODEL;
  if (!key || key.startsWith('replace-with-') || !model || model.startsWith('replace-with-')) throw Object.assign(new Error('NVIDIA provider configuration unavailable.'), { safeCode: 'configuration_unavailable' });
  const endpoint = env.AI_PROVIDER_URL || contract.settings.default_endpoint;
  const timeout = Number(env.NVIDIA_NIM_TIMEOUT_MS || contract.settings.timeout_ms);
  if (timeout !== 18000) throw new Error('This frozen experiment requires the production baseline 18,000 ms timeout.');
  return { key, model, endpoint, timeout };
}

function loadRequestBudget() {
  let observedLegacyCount = 0;
  let count = 0;
  if (!fs.existsSync(RUN_DIR)) return 13;
  for (const name of fs.readdirSync(RUN_DIR).filter((n) => n.endsWith('.jsonl'))) {
    const file = path.join(RUN_DIR, name);
    const text = read(file);
    if (name === 'baseline-development.jsonl') {
      const rows = text.split(/\r?\n/).filter(Boolean).slice(1).map((line) => JSON.parse(line));
      const attempted = rows.filter((row) => row.request_attempted === true).length;
      if (attempted !== 13) throw new Error('Historical v1 request ledger no longer has its original 13 observations; refusing budget calculation.');
      observedLegacyCount = attempted;
    } else if (name.startsWith('baseline-v2-')) {
      const rows = text.split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
      count += rows.slice(1).filter((row) => row.kind === 'reservation').length;
    }
  }
  // The original 13 observations remain charged even when evaluation runs only from the protected volume.
  return Math.max(count + observedLegacyCount, 13);
}

function responseRecord(responseJson, item, input, contract, manifest, context, latencyMs) {
  let outcome;
  let errorClass = null;
  let status = responseJson?.status ?? null;
  const body = responseJson?.body;
  if (status < 200 || status >= 300) { outcome = 'provider_failure'; errorClass = `http_${status}`; }
  else if (!body || typeof body !== 'object') { outcome = 'invalid_output'; errorClass = 'malformed_provider_json'; }
  else {
    const validated = validatePayload(body, contract, input);
    if (validated.ai_status !== 'enriched') { outcome = 'invalid_output'; errorClass = 'application_schema_invalid'; }
    else outcome = 'usable_output';
  }
  const validated = outcome === 'usable_output' ? validatePayload(body, contract, input) : null;
  const rawExtracted = validated?.enrichment ?? null;
  const redact = (value) => typeof value === 'string' ? value.replace(/(?:nvapi|sk)-[A-Za-z0-9_-]{16,}/gi, '[REDACTED_TOKEN]').replace(/Bearer\s+[A-Za-z0-9._~+/-]{12,}/gi, 'Bearer [REDACTED]').replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[REDACTED_EMAIL]') : value;
  const extracted = rawExtracted ? Object.fromEntries(Object.entries(rawExtracted).map(([key, value]) => [key, redact(value)])) : null;
  const content = body?.choices?.[0]?.message?.content;
  const safeContent = redact(content);
  const usage = body?.usage && typeof body.usage === 'object' ? {
    prompt_tokens: Number.isFinite(body.usage.prompt_tokens) ? body.usage.prompt_tokens : null,
    completion_tokens: Number.isFinite(body.usage.completion_tokens) ? body.usage.completion_tokens : null,
    total_tokens: Number.isFinite(body.usage.total_tokens) ? body.usage.total_tokens : null
  } : null;
  const grading = extracted ? gradeCase(item, validated) : null;
  return {
    ...context, kind: 'settlement', outcome, http_status: status,
    error_class: errorClass,
    extracted,
    raw_model_content: safeContent,
    response_content_hash: typeof content === 'string' ? sha256(content) : null,
    grading,
    latency_ms: latencyMs,
    token_usage: usage
  };
}

async function oneAttempt({ file, manifest, runId, split, item, key, endpoint, timeout, contract, transport = fetch, hooks = {} }) {
  const context = eventContext(manifest, runId, split, item);
  const requestId = crypto.randomUUID();
  appendDurable(file, { ...context, kind: 'reservation', request_id: requestId, reserved_at: new Date().toISOString() });
  await hooks.afterReservation?.();
  appendDurable(file, { ...context, kind: 'sent', request_id: requestId, sent_at: new Date().toISOString() });
  const started = performance.now();
  let result;
  try {
    const requestBody = {
      model: manifest.model,
      ...manifest.inference_settings,
      messages: [{ role: 'system', content: contract.prompt }, { role: 'user', content: item.input.trim() }]
    };
    const response = await transport(endpoint, {
      method: 'POST',
      headers: { authorization: `Bearer ${key}`, 'content-type': 'application/json' },
      body: JSON.stringify(requestBody),
      signal: AbortSignal.timeout(timeout)
    });
    let body;
    try { body = await response.json(); } catch { body = null; }
    result = responseRecord({ status: response.status, body }, item, item.input.trim(), contract, manifest, { ...context, request_id: requestId }, Math.round(performance.now() - started));
  } catch (error) {
    if (error?.simulatedCrash) throw error;
    const timeoutFailure = error?.name === 'TimeoutError' || error?.name === 'AbortError';
    const network = error?.cause?.code;
    result = {
      ...context, kind: 'settlement', request_id: requestId,
      outcome: timeoutFailure ? 'timeout' : 'provider_failure',
      http_status: null,
      error_class: timeoutFailure ? 'timeout' : network === 'ENOTFOUND' ? 'dns_failure' : network === 'ECONNREFUSED' ? 'connection_refused' : 'network_error',
      extracted: null, raw_model_content: null, response_content_hash: null, grading: null,
      latency_ms: Math.round(performance.now() - started), token_usage: null
    };
  }
  result.request_id = requestId;
  result.settled_at = new Date().toISOString();
  appendDurable(file, result);
  return result;
}

async function runLive(split, runId) {
  const data = loadDataset();
  const contract = readContract();
  const config = loadApiConfig(contract);
  const settings = {
    temperature: contract.settings.temperature,
    max_tokens: contract.settings.max_tokens,
    reasoning_effort: contract.settings.reasoning_effort,
    response_format: contract.settings.response_format
  };
  const manifest = makeManifest({
    provider: 'nvidia_nim', model: config.model, endpoint: config.endpoint,
    settings, timeoutMs: config.timeout, datasetHash: data.datasetHash,
    rubricHash: sha256(read(RUBRIC)), contract
  });
  if (!['development', 'held_out'].includes(split) || runId !== `baseline-v2-${split}`) throw new Error('Run ID must be baseline-v2-development or baseline-v2-held_out and match split.');
  if (split === 'held_out') {
    const devFile = path.join(RUN_DIR, 'baseline-v2-development.jsonl');
    if (!fs.existsSync(devFile)) throw new Error('Held-out evaluation requires a completed development run.');
    const dev = parseAndValidateLedger({ text: read(devFile), dataset: data, expectedManifest: manifest, expectedSplit: 'development' });
    const expectedN = data.dataset.cases.filter((i) => i.split === 'development').length;
    if (dev.attempts.length !== expectedN || dev.attempts.some((a) => !a.settlement)) throw new Error('Held-out evaluation requires every development case to have a settled outcome.');
  }
  fs.mkdirSync(RUN_DIR, { recursive: true });
  const unlock = acquireLock(path.join(RUN_DIR, '.milestone-2a-v2.lock'));
  try {
    const file = path.join(RUN_DIR, `${runId}.jsonl`);
    let validated;
    if (fs.existsSync(file)) validated = parseAndValidateLedger({ text: read(file), dataset: data, expectedManifest: manifest, expectedSplit: split, expectedRunId: runId });
    else {
      const header = { kind: 'header', run_id: runId, split, created_at: new Date().toISOString(), manifest, manifest_hash: manifestHash(manifest) };
      const fd = fs.openSync(file, 'wx', 0o600);
      try { fs.writeSync(fd, `${JSON.stringify(header)}\n`); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
      validated = parseAndValidateLedger({ text: read(file), dataset: data, expectedManifest: manifest, expectedSplit: split, expectedRunId: runId });
    }
    const reserved = new Set(validated.attempts.map((a) => a.reservation.case_id));
    const pending = data.dataset.cases.filter((item) => item.split === split && !reserved.has(item.id));
    let consecutiveServiceFailures = 0;
    const settlements = validated.attempts.map((a) => a.settlement).filter(Boolean);
    for (const prior of settlements.slice(-3)) {
      if (prior.outcome === 'provider_failure' || prior.outcome === 'timeout') consecutiveServiceFailures += 1;
      else consecutiveServiceFailures = 0;
    }
    if (consecutiveServiceFailures >= 3) throw new Error('Circuit breaker is open after three consecutive timeout/provider failures. Diagnose service, then invoke with --ack-circuit-reset to resume only unreserved cases.');
    if (process.argv.includes('--ack-circuit-reset')) consecutiveServiceFailures = 0;
    for (const item of pending) {
      const outcome = await budgetedAttempt({ used: loadRequestBudget(), file, manifest, runId, split, item, key: config.key, endpoint: config.endpoint, timeout: config.timeout, contract });
      process.stdout.write(`${item.id}: ${outcome.outcome}\n`);
      const confirmedConfiguration = [400, 401, 403, 404, 422].includes(outcome.http_status);
      if (confirmedConfiguration) {
        process.stdout.write('Stopping immediately after confirmed authentication/endpoint configuration failure.\n');
        break;
      }
      if (outcome.outcome === 'provider_failure' || outcome.outcome === 'timeout') consecutiveServiceFailures += 1;
      else consecutiveServiceFailures = 0;
      if (consecutiveServiceFailures >= 3) {
        process.stdout.write('Circuit breaker opened after three consecutive timeout/provider failures; remaining cases stay unreserved.\n');
        break;
      }
    }
    const final = parseAndValidateLedger({ text: read(file), dataset: data, expectedManifest: manifest, expectedSplit: split, expectedRunId: runId });
    process.stdout.write(`Retained ${final.attempts.length} reservations; ${final.attempts.filter((a) => !a.settlement).length} uncertain outcomes.\n`);
  } finally { unlock(); }
}

function validateCommand() {
  const data = loadDataset();
  const contract = readContract();
  if (data.dataset.cases.length !== 60 || data.dataset.cases.filter((x) => x.split === 'development').length !== 40 || data.dataset.cases.filter((x) => x.split === 'held_out').length !== 20) throw new Error('Dataset v2 split/count validation failed.');
  const ids = new Set();
  for (const item of data.dataset.cases) {
    if (ids.has(item.id) || !item.rationale || !item.expected || !Array.isArray(item.forbidden)) throw new Error(`Invalid case ${item.id}.`);
    ids.add(item.id);
    for (const field of CASES) if (!Object.hasOwn(item.expected, field)) throw new Error(`Case ${item.id} missing ${field}.`);
  }
  const rubric = JSON.parse(read(RUBRIC));
  if (rubric.version !== 'synthetic-rubric-v2' || rubric.changes_from_v1.length !== 4) throw new Error('Rubric v2 revision metadata invalid.');
  process.stdout.write(`Valid ${data.dataset.version}: ${ids.size} cases (${data.dataset.cases.filter((x) => x.split === 'development').length} development, ${data.dataset.cases.filter((x) => x.split === 'held_out').length} held_out).\n`);
  process.stdout.write(`effective_dataset_sha256=${data.datasetHash}\nrubric_sha256=${sha256(read(RUBRIC))}\nprompt_sha256=${contract.promptHash}\ncontract_sha256=${contract.contractHash}\n`);
}

function reportCommand() {
  const data = loadDataset();
  const runs = validateRecordsForReport(data, ['baseline-v2-development', 'baseline-v2-held_out']);
  const text = formatReport(runs, data);
  const output = path.join(ROOT, 'docs/reviews/milestone-2a-results-v2.md');
  fs.writeFileSync(output, text);
  process.stdout.write(`Wrote ${path.relative(ROOT, output)}\n`);
}

export {
  acquireLock, assertRequestBudget, budgetedAttempt, deriveStats, endpointIdentity, eventContext, formatReport, gradeCase,
  loadDataset, makeManifest, manifestHash, oneAttempt, parseAndValidateLedger,
  pendingCases, responseRecord, stableJson, validateRecordsForReport
};

const [command, ...args] = process.argv.slice(2);
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) try {
  if (command === 'validate') validateCommand();
  else if (command === 'run') {
    const split = args[args.indexOf('--split') + 1];
    const runId = args[args.indexOf('--run-id') + 1];
    await runLive(split, runId);
  } else if (command === 'report') reportCommand();
  else throw new Error('Commands: validate | run --split development|held_out --run-id baseline-v2-development|baseline-v2-held_out | report');
} catch (error) {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = error?.safeCode === 'configuration_unavailable' ? 3 : 1;
}
