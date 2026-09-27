#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DATASET_PATH = path.join(ROOT, 'n8n/evaluation/dataset-v1.json');
const RUBRIC_PATH = path.join(ROOT, 'n8n/evaluation/rubric-v1.json');
const WORKFLOW_PATH = path.join(ROOT, 'n8n/lead-intake.json');
const RUN_DIR = process.env.AI_EVAL_RUN_DIR
  ? path.resolve(process.env.AI_EVAL_RUN_DIR)
  : path.join(ROOT, 'docs/reviews/ai-evaluation-runs');
const FIELD_NAMES = ['service_type', 'location', 'preferred_time', 'urgency', 'summary'];
const GRADED_FIELDS = ['service_type', 'location', 'preferred_time', 'urgency'];
const SERVICE_TYPES = ['furnace_service', 'air_conditioning_service', 'plumbing_service', 'electrical_service', 'general_home_service', 'unknown'];
const URGENCY_VALUES = ['low', 'medium', 'high', 'urgent'];
const sha256 = (value) => crypto.createHash('sha256').update(value).digest('hex');
const read = (file) => fs.readFileSync(file, 'utf8');

function loadProtectedEnv() {
  const values = {};
  const dotenvPath = path.join(ROOT, '.env');
  if (fs.existsSync(dotenvPath)) {
    for (const line of read(dotenvPath).split(/\r?\n/)) {
      const match = line.match(/^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/);
      if (!match) continue;
      let value = match[2];
      if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) value = value.slice(1, -1);
      values[match[1]] = value;
    }
  }
  return { ...values, ...process.env };
}

function readContract() {
  const workflow = JSON.parse(read(WORKFLOW_PATH));
  const nodes = Object.fromEntries(workflow.nodes.map((node) => [node.name, node]));
  const requestNode = nodes['Extract Service Context with NVIDIA NIM'];
  const validatorNode = nodes['Validate AI Extraction'];
  if (!requestNode || !validatorNode) throw new Error('Exported extraction nodes are missing.');
  const expression = requestNode.parameters.jsonBody;
  const endpointMatch = requestNode.parameters.url.match(/\|\|\s*'([^']+)'/);
  if (!endpointMatch) throw new Error('Could not read the exported default provider endpoint.');
  const promptMatch = expression.match(/role:\s*'system',\s*content:\s*'((?:\\.|[^'])*)'/);
  if (!promptMatch) throw new Error('Could not safely extract the literal system prompt from workflow export.');
  const prompt = promptMatch[1].replaceAll("\\'", "'").replaceAll('\\n', '\n').replaceAll('\\\\', '\\');
  const getNumber = (pattern, name) => {
    const match = expression.match(pattern);
    if (!match) throw new Error(`Could not read exported ${name} setting.`);
    return Number(match[1]);
  };
  const temperature = getNumber(/temperature:\s*(\d+(?:\.\d+)?)/, 'temperature');
  const maxTokens = getNumber(/max_tokens:\s*(\d+)/, 'max_tokens');
  const reasoningMatch = expression.match(/reasoning_effort:\s*'([^']+)'/);
  const timeoutMatch = requestNode.parameters.options.timeout.match(/\|\|\s*(\d+)/);
  const formatMatch = expression.match(/response_format:\s*\{\s*type:\s*'([^']+)'/);
  if (!reasoningMatch || !timeoutMatch || !formatMatch) throw new Error('Exported request settings are incomplete.');
  const validator = validatorNode.parameters.jsCode;
  const exactKeysMatch = validator.match(/const exactKeys = \[([^\]]+)\]/);
  if (!exactKeysMatch) throw new Error('Could not read the exported validator field contract.');
  const contractKeys = [...exactKeysMatch[1].matchAll(/'([^']+)'/g)].map((match) => match[1]);
  if (JSON.stringify(contractKeys) !== JSON.stringify(FIELD_NAMES)) throw new Error('Evaluator field list drifted from exported validator.');
  return {
    workflow,
    requestNode,
    validator,
    prompt,
    settings: {
      temperature,
      max_tokens: maxTokens,
      reasoning_effort: reasoningMatch[1],
      response_format: { type: formatMatch[1] },
      timeout_ms: Number(timeoutMatch[1]),
      default_endpoint: endpointMatch[1],
      endpoint_template: requestNode.parameters.url,
      fields: contractKeys
    },
    promptHash: sha256(prompt),
    contractHash: sha256(`${prompt}\n${validator}\n${expression}\n${JSON.stringify(requestNode.parameters.options)}`)
  };
}

function validateDataset(dataset, rubric) {
  const errors = [];
  const cases = dataset?.cases;
  if (!Array.isArray(cases)) return ['cases must be an array'];
  const ids = new Set();
  const counts = { development: 0, held_out: 0 };
  for (const [index, item] of cases.entries()) {
    const label = `case[${index}]`;
    if (!item || typeof item !== 'object') { errors.push(`${label} must be an object`); continue; }
    if (!/^[A-Z][0-9]{3}$/.test(item.id) || ids.has(item.id)) errors.push(`${label} has invalid or duplicate ID`);
    ids.add(item.id);
    if (!['development', 'held_out'].includes(item.split)) errors.push(`${label} has invalid split`);
    else counts[item.split] += 1;
    if (typeof item.category !== 'string' || !item.category.trim()) errors.push(`${label} has no category`);
    if (typeof item.input !== 'string' || !item.input.trim()) errors.push(`${label} has no input`);
    if (!item.expected || typeof item.expected !== 'object') errors.push(`${label} has no expected object`);
    else {
      for (const field of GRADED_FIELDS) {
        const expected = item.expected[field];
        if (expected === undefined || !(expected === null || typeof expected === 'string' || (Array.isArray(expected) && expected.every((x) => typeof x === 'string' || x === null)))) errors.push(`${label}.${field} has invalid expected value`);
        const options = Array.isArray(expected) ? expected : [expected];
        if (field === 'service_type' && options.some((value) => !SERVICE_TYPES.includes(value))) errors.push(`${label}.${field} has an unsupported enum`);
        if (field === 'urgency' && options.some((value) => !URGENCY_VALUES.includes(value))) errors.push(`${label}.${field} has an unsupported enum`);
        if ((field === 'location' || field === 'preferred_time') && options.some((value) => value !== null && (!value.trim() || value.length > 160))) errors.push(`${label}.${field} must be null or non-empty text up to 160 characters`);
      }
      if (Object.keys(item.expected).some((key) => !GRADED_FIELDS.includes(key))) errors.push(`${label} contains unsupported expected field`);
    }
    if (typeof item.rationale !== 'string' || !item.rationale.trim()) errors.push(`${label} needs a grading rationale`);
    if (!Array.isArray(item.forbidden) || item.forbidden.some((value) => typeof value !== 'string')) errors.push(`${label} needs forbidden-fact notes`);
    if (item.summary_mode !== 'review') errors.push(`${label} summary must be marked for review`);
  }
  if (cases.length !== 60) errors.push(`expected exactly 60 cases; found ${cases.length}`);
  if (counts.development !== 40 || counts.held_out !== 20) errors.push(`expected 40 development and 20 held_out; found ${counts.development}/${counts.held_out}`);
  if (!rubric || rubric.version !== 'synthetic-rubric-v1') errors.push('rubric version is missing or unsupported');
  return errors;
}

function canonicalText(value) {
  return typeof value === 'string' ? value.trim().toLocaleLowerCase('en').replace(/\s+/g, ' ') : value;
}

function expectedMatches(actual, expected, field) {
  const options = Array.isArray(expected) ? expected : [expected];
  return options.some((item) => field === 'location' || field === 'preferred_time'
    ? canonicalText(actual) === canonicalText(item)
    : actual === item);
}

function runExportedValidator(contract, response, syntheticMessage) {
  const source = `(function(){\n${contract.validator}\n})()`;
  const context = {
    $json: response,
    $env: { NVIDIA_NIM_MODEL: 'evaluation-model' },
    $execution: { id: 'offline-evaluation' },
    $: () => ({ first: () => ({ json: { lead: { normalized_message: syntheticMessage } } }) })
  };
  return vm.runInNewContext(source, context, { timeout: 100 })[0].json.crmPayload;
}

const prohibitedClaimPattern = /\$\s*\d|\b(?:confirmed|booked)\s+(?:for|at|on)\b|\b(?:guaranteed|available)\s+(?:today|tomorrow|at\s+\d|on\s+\w+)/i;

function gradeCase(item, responsePayload) {
  const extracted = responsePayload.enrichment;
  const fieldResults = {};
  for (const field of GRADED_FIELDS) {
    const actual = extracted?.[field];
    fieldResults[field] = extracted !== null && expectedMatches(actual, item.expected[field], field);
  }
  const safeOutput = extracted ? JSON.stringify(extracted) : '';
  const prohibitedClaim = prohibitedClaimPattern.test(safeOutput);
  const automaticSemanticCorrect = Object.values(fieldResults).every(Boolean) && !prohibitedClaim;
  return {
    field_results: fieldResults,
    prohibited_claim_detected: prohibitedClaim,
    automatic_semantic_correct: automaticSemanticCorrect,
    summary_review_required: true
  };
}

function validateProviderPayload(responsePayload, contract, syntheticMessage) {
  try {
    return runExportedValidator(contract, responsePayload, syntheticMessage);
  } catch {
    return { enrichment: null, ai_status: 'fallback_invalid' };
  }
}

function summarize(records, categories = []) {
  const attempted = records.length;
  const returned = records.filter((record) => record.http_status >= 200 && record.http_status < 300);
  const usable = records.filter((record) => record.outcome === 'usable_output');
  const fieldStats = Object.fromEntries(GRADED_FIELDS.map((field) => {
    const correct = usable.filter((record) => record.grading.field_results[field]).length;
    return [field, { correct, denominator: usable.length, percent: usable.length ? correct / usable.length * 100 : null }];
  }));
  const semanticCorrect = usable.filter((record) => record.grading.automatic_semantic_correct).length;
  return {
    attempted,
    provider_available: returned.length,
    provider_availability_denominator: attempted,
    schema_valid: usable.length,
    schema_denominator: returned.length,
    semantic_correct: semanticCorrect,
    semantic_denominator: usable.length,
    overall_success: semanticCorrect,
    overall_denominator: attempted,
    outcomes: Object.fromEntries(['usable_output', 'invalid_output', 'timeout', 'provider_failure'].map((name) => [name, records.filter((record) => record.outcome === name).length])),
    fields: fieldStats,
    summary_review_required: usable.length,
    category: Object.fromEntries([...new Set([...categories, ...records.map((record) => record.category)])].sort().map((category) => {
      const selected = records.filter((record) => record.category === category);
      const selectedUsable = selected.filter((record) => record.outcome === 'usable_output');
      const n = selected.length;
      const correct = selectedUsable.filter((record) => record.grading.automatic_semantic_correct).length;
      return [category, { attempted: n, usable: selectedUsable.length, automatic_semantic_correct: correct, all_attempts_denominator: n }];
    }))
  };
}

function pct(numerator, denominator) {
  return denominator ? `${(100 * numerator / denominator).toFixed(1)}% (${numerator}/${denominator})` : `n/a (0/${denominator})`;
}

function usageAndLatency(records) {
  const usage = records.map((record) => record.token_usage).filter((value) => value && Number.isFinite(value.total_tokens));
  const latencies = records.map((record) => record.latency_ms).filter(Number.isFinite).sort((a, b) => a - b);
  const median = latencies.length ? latencies[Math.floor(latencies.length / 2)] : null;
  return {
    responses_with_usage: usage.length,
    prompt_tokens: usage.reduce((sum, value) => sum + (value.prompt_tokens ?? 0), 0),
    completion_tokens: usage.reduce((sum, value) => sum + (value.completion_tokens ?? 0), 0),
    total_tokens: usage.reduce((sum, value) => sum + (value.total_tokens ?? 0), 0),
    median_latency_ms: median
  };
}

function reportSection(title, records, categories) {
  const m = summarize(records, categories);
  const usage = usageAndLatency(records);
  const lines = [
    `### ${title}`,
    '',
    `- Provider availability (HTTP 2xx / attempted): ${pct(m.provider_available, m.provider_availability_denominator)}`,
    `- Schema valid (usable / HTTP 2xx): ${pct(m.schema_valid, m.schema_denominator)}`,
    `- Automatic semantic correctness (all four auto-graded fields and no detected prohibited claim / usable): ${pct(m.semantic_correct, m.semantic_denominator)}`,
    `- Overall success (automatic semantic successes / all attempted): ${pct(m.overall_success, m.overall_denominator)}`,
    `- Outcomes: usable ${m.outcomes.usable_output}, invalid ${m.outcomes.invalid_output}, timeout ${m.outcomes.timeout}, provider failure ${m.outcomes.provider_failure} (n=${m.attempted})`,
    `- Returned token usage: ${usage.responses_with_usage}/${m.attempted} attempts; prompt ${usage.prompt_tokens}, completion ${usage.completion_tokens}, total ${usage.total_tokens}. Median latency: ${usage.median_latency_ms === null ? 'n/a' : `${usage.median_latency_ms} ms`} across ${m.attempted} attempts.`,
    `- Summary semantic review required: ${m.summary_review_required}/${m.schema_valid} usable outputs; not included in automatic semantic accuracy.`,
    '',
    '| Field | Correct among usable |',
    '|---|---:|',
    ...GRADED_FIELDS.map((field) => `| ${field} | ${pct(m.fields[field].correct, m.fields[field].denominator)} |`),
    '',
    '| Category | Automatic semantic correct / attempted |',
    '|---|---:|',
    ...Object.entries(m.category).map(([category, value]) => `| ${category} | ${value.automatic_semantic_correct}/${value.all_attempts_denominator} |`),
    ''
  ];
  return lines.join('\n');
}

function loadLedger(file, expectedHeader) {
  if (!fs.existsSync(file)) return { header: expectedHeader, records: [] };
  const rows = read(file).split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
  if (!rows.length || rows[0].kind !== 'header') throw new Error(`Ledger ${path.basename(file)} has no compatible header.`);
  for (const key of ['dataset_hash', 'rubric_hash', 'prompt_hash', 'contract_hash', 'split', 'run_id']) {
    if (rows[0][key] !== expectedHeader[key]) throw new Error(`Ledger ${path.basename(file)} is incompatible on ${key}; refusing to mix versions.`);
  }
  const records = rows.slice(1);
  if (new Set(records.map((record) => record.case_id)).size !== records.length) throw new Error(`Ledger ${path.basename(file)} contains duplicate case records.`);
  return { header: rows[0], records };
}

function pendingCases(selected, records) {
  const completed = new Set(records.map((record) => record.case_id));
  return selected.filter((item) => !completed.has(item.id));
}

function assertRunCompatible(header, expectedHeader) {
  for (const key of ['dataset_hash', 'rubric_hash', 'prompt_hash', 'contract_hash', 'split', 'run_id']) {
    if (header[key] !== expectedHeader[key]) throw new Error(`Ledger is incompatible on ${key}; refusing to mix versions.`);
  }
}

async function runLive(split, runId) {
  const datasetText = read(DATASET_PATH);
  const dataset = JSON.parse(datasetText);
  const rubric = JSON.parse(read(RUBRIC_PATH));
  const issues = validateDataset(dataset, rubric);
  if (issues.length) throw new Error(`Dataset validation failed: ${issues.join('; ')}`);
  const contract = readContract();
  const env = loadProtectedEnv();
  const key = env.NVIDIA_NIM_API_KEY;
  const model = env.NVIDIA_NIM_MODEL;
  if (!key || key.startsWith('replace-with-') || !model || model.startsWith('replace-with-')) {
    throw Object.assign(new Error('NVIDIA provider configuration is unavailable (missing or placeholder key/model).'), { safeCode: 'configuration_unavailable' });
  }
  const endpoint = env.AI_PROVIDER_URL || contract.settings.default_endpoint;
  const timeoutMs = Number(env.NVIDIA_NIM_TIMEOUT_MS || contract.settings.timeout_ms);
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 100 || timeoutMs > 60000) throw new Error('Configured provider timeout is outside the evaluator bounds.');
  let endpointUrl;
  try { endpointUrl = new URL(endpoint); } catch { throw new Error('Configured provider endpoint is invalid.'); }
  if (endpointUrl.protocol !== 'https:') throw new Error('Provider endpoint must use HTTPS.');
  const selected = dataset.cases.filter((item) => item.split === split);
  const expectedRunId = split === 'development' ? 'baseline-development' : 'baseline-held-out';
  if (runId !== expectedRunId) throw new Error(`This milestone supports only ${expectedRunId} for the ${split} baseline.`);
  if (split === 'held_out') {
    const development = loadLedger(path.join(RUN_DIR, 'baseline-development.jsonl'), {
      dataset_hash: sha256(datasetText), rubric_hash: sha256(read(RUBRIC_PATH)),
      prompt_hash: contract.promptHash, contract_hash: contract.contractHash,
      split: 'development', run_id: 'baseline-development'
    });
    const devCases = dataset.cases.filter((item) => item.split === 'development');
    if (pendingCases(devCases, development.records).length !== 0) throw new Error('Held-out calls require all 40 development cases to be completed first.');
  }
  const ledgerPath = path.join(RUN_DIR, `${runId}.jsonl`);
  fs.mkdirSync(RUN_DIR, { recursive: true });
  const header = {
    kind: 'header', run_id: runId, split,
    created_at: new Date().toISOString(),
    dataset_version: dataset.version, dataset_hash: sha256(datasetText),
    rubric_version: rubric.version, rubric_hash: sha256(read(RUBRIC_PATH)),
    provider: 'nvidia_nim', model_id: model,
    prompt_hash: contract.promptHash, contract_hash: contract.contractHash,
    request_settings: { ...contract.settings, timeout_ms: timeoutMs, endpoint_host: endpointUrl.host, endpoint_path: endpointUrl.pathname },
    provider_call_cap: 150
  };
  const { records } = loadLedger(ledgerPath, header);
  const pending = pendingCases(selected, records);
  if (pending.length === 0) {
    process.stdout.write(`All ${records.length} cases are already recorded for ${runId}; no provider calls made.\n`);
    return;
  }
  const totalCalls = fs.existsSync(RUN_DIR) ? fs.readdirSync(RUN_DIR).filter((name) => name.endsWith('.jsonl')).reduce((sum, name) => {
    const entries = read(path.join(RUN_DIR, name)).split(/\r?\n/).filter(Boolean);
    return sum + entries.slice(1).filter((line) => { try { return JSON.parse(line).request_attempted; } catch { return false; } }).length;
  }, 0) : 0;
  if (totalCalls >= 150) throw new Error('The persistent provider-call cap of 150 has been reached.');
  if (!fs.existsSync(ledgerPath)) fs.writeFileSync(ledgerPath, `${JSON.stringify(header)}\n`, { flag: 'wx', mode: 0o600 });
  let newCalls = 0;
  for (const item of pending) {
    if (totalCalls + newCalls >= 150) throw new Error('The persistent provider-call cap of 150 has been reached.');
    const inputHash = sha256(item.input);
    const inputMessage = item.input.trim();
    const requestBody = {
      model,
      temperature: contract.settings.temperature,
      max_tokens: contract.settings.max_tokens,
      reasoning_effort: contract.settings.reasoning_effort,
      response_format: contract.settings.response_format,
      messages: [{ role: 'system', content: contract.prompt }, { role: 'user', content: inputMessage }]
    };
    const started = performance.now();
    let httpStatus = null;
    let rawText = '';
    let responseJson = null;
    let outcome;
    let errorClass = null;
    try {
      const response = await fetch(endpointUrl, {
        method: 'POST',
        headers: { authorization: `Bearer ${key}`, 'content-type': 'application/json' },
        body: JSON.stringify(requestBody),
        signal: AbortSignal.timeout(timeoutMs)
      });
      httpStatus = response.status;
      rawText = await response.text();
      if (httpStatus < 200 || httpStatus >= 300) {
        outcome = 'provider_failure';
        errorClass = `http_${httpStatus}`;
      } else {
        try { responseJson = JSON.parse(rawText); } catch { outcome = 'invalid_output'; errorClass = 'malformed_provider_json'; }
        if (responseJson) {
          if (responseJson.error) { outcome = 'provider_failure'; errorClass = 'provider_error_object'; }
          else outcome = 'received';
        }
      }
    } catch (error) {
      const timedOut = error?.name === 'TimeoutError' || error?.name === 'AbortError';
      outcome = timedOut ? 'timeout' : 'provider_failure';
      errorClass = timedOut ? 'timeout' : error?.cause?.code === 'ENOTFOUND' ? 'dns_failure' : error?.cause?.code === 'ECONNREFUSED' ? 'connection_refused' : 'network_error';
    }
    const latencyMs = Math.round(performance.now() - started);
    let payload = null;
    let extracted = null;
    let usage = null;
    if (outcome === 'received') {
      const validated = validateProviderPayload(responseJson, contract, inputMessage);
      if (validated.ai_status === 'enriched') {
        outcome = 'usable_output';
        payload = validated;
        extracted = validated.enrichment;
      } else {
        outcome = 'invalid_output';
        errorClass = 'application_schema_invalid';
      }
      if (responseJson?.usage && typeof responseJson.usage === 'object') {
        usage = {
          prompt_tokens: Number.isFinite(responseJson.usage.prompt_tokens) ? responseJson.usage.prompt_tokens : null,
          completion_tokens: Number.isFinite(responseJson.usage.completion_tokens) ? responseJson.usage.completion_tokens : null,
          total_tokens: Number.isFinite(responseJson.usage.total_tokens) ? responseJson.usage.total_tokens : null
        };
      }
    } else if (responseJson?.usage) {
      usage = { prompt_tokens: null, completion_tokens: null, total_tokens: null };
    }
    const content = responseJson?.choices?.[0]?.message?.content;
    const safeContent = typeof content === 'string' ? content
      .replace(/(?:nvapi|sk)-[A-Za-z0-9_-]{16,}/gi, '[REDACTED_TOKEN]')
      .replace(/Bearer\s+[A-Za-z0-9._~+/-]{12,}/gi, 'Bearer [REDACTED]')
      .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[REDACTED_EMAIL]') : null;
    const safeExtracted = extracted ? Object.fromEntries(FIELD_NAMES.map((field) => [field, typeof extracted[field] === 'string'
      ? extracted[field].replace(/(?:nvapi|sk)-[A-Za-z0-9_-]{16,}/gi, '[REDACTED_TOKEN]').replace(/Bearer\s+[A-Za-z0-9._~+/-]{12,}/gi, 'Bearer [REDACTED]').replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[REDACTED_EMAIL]')
      : extracted[field]])) : null;
    const gradingPayload = payload ? { ...payload, enrichment: safeExtracted } : null;
    const grading = gradingPayload ? gradeCase(item, gradingPayload) : { field_results: Object.fromEntries(GRADED_FIELDS.map((field) => [field, false])), prohibited_claim_detected: false, automatic_semantic_correct: false, summary_review_required: false };
    const record = {
      case_id: item.id, category: item.category, split, dataset_hash: sha256(datasetText), input_hash: inputHash,
      provider: 'nvidia_nim', model_id: model,
      prompt_hash: contract.promptHash, contract_hash: contract.contractHash,
      request_settings: { temperature: requestBody.temperature, max_tokens: requestBody.max_tokens, reasoning_effort: requestBody.reasoning_effort, response_format: requestBody.response_format, timeout_ms: timeoutMs },
      request_attempted: true, outcome, http_status: httpStatus, error_class: errorClass,
      extracted: safeExtracted, raw_model_content: safeContent,
      response_content_hash: typeof content === 'string' ? sha256(content) : null,
      grading, latency_ms: latencyMs, token_usage: usage
    };
    fs.appendFileSync(ledgerPath, `${JSON.stringify(record)}\n`, { mode: 0o600 });
    records.push(record);
    newCalls += 1;
    process.stdout.write(`${item.id}: ${outcome}\n`);
    if (outcome === 'timeout' || outcome === 'provider_failure') {
      process.stdout.write('Stopping after provider access failure; resume will preserve this result and continue with unattempted cases.\n');
      break;
    }
  }
  process.stdout.write(`Saved ${records.length} case records to ${path.relative(ROOT, ledgerPath)}\n`);
}

function readRun(runId) {
  const file = path.join(RUN_DIR, `${runId}.jsonl`);
  if (!fs.existsSync(file)) return null;
  const rows = read(file).split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
  const header = rows.shift();
  const datasetHash = sha256(read(DATASET_PATH));
  const contract = readContract();
  const rubricHash = sha256(read(RUBRIC_PATH));
  if (header.dataset_hash !== datasetHash || header.rubric_hash !== rubricHash || header.prompt_hash !== contract.promptHash || header.contract_hash !== contract.contractHash) {
    throw new Error(`Run ${runId} has incompatible dataset or prompt/contract hashes.`);
  }
  const expected = JSON.parse(read(DATASET_PATH)).cases.filter((item) => item.split === header.split);
  const byId = new Map(rows.map((record) => [record.case_id, record]));
  const ordered = expected.map((item) => byId.get(item.id)).filter(Boolean);
  return { header, records: ordered };
}

function generateReport() {
  const datasetText = read(DATASET_PATH);
  const dataset = JSON.parse(datasetText);
  const rubric = JSON.parse(read(RUBRIC_PATH));
  const contract = readContract();
  const dev = readRun('baseline-development');
  const held = readRun('baseline-held-out');
  const runs = [dev, held].filter(Boolean);
  const rows = runs.flatMap((run) => run.records);
  const categoryCounts = Object.fromEntries([...new Set(dataset.cases.map((item) => item.category))].sort().map((category) => [category, {
    development: dataset.cases.filter((item) => item.category === category && item.split === 'development').length,
    held_out: dataset.cases.filter((item) => item.category === category && item.split === 'held_out').length
  }]));
  const lines = [
    '# Milestone 2A AI extraction evaluation', '',
    `Status: ${runs.length === 2 && rows.length === 60 ? 'measured baseline' : runs.length ? 'partial live evaluation' : 'live evaluation blocked; offline harness ready'}.`, '',
    `Dataset: ${dataset.version}, SHA-256 \`${sha256(datasetText)}\` (${dataset.cases.length} cases: ${dataset.cases.filter((x) => x.split === 'development').length} development, ${dataset.cases.filter((x) => x.split === 'held_out').length} held out).`,
    `Rubric: ${rubric.version}, SHA-256 \`${sha256(read(RUBRIC_PATH))}\`.`,
    `Exported system prompt SHA-256: \`${contract.promptHash}\`; extraction request/validator contract SHA-256: \`${contract.contractHash}\`.`,
    `Model: ${runs[0]?.header.model_id ?? 'not run (no configured provider key/model available)'}. Provider: NVIDIA NIM OpenAI-compatible chat completions.`,
    `Run identifiers: ${runs.map((run) => run.header.run_id).join(', ') || 'no run artifacts'}. Held-out run: ${held ? held.header.run_id : 'not run'}.`,
    `Exported request settings: temperature=${contract.settings.temperature}, max_tokens=${contract.settings.max_tokens}, reasoning_effort=${contract.settings.reasoning_effort}, response_format=${contract.settings.response_format.type}, timeout=${contract.settings.timeout_ms} ms; sequential concurrency=1.`,
    `Provider requests made: ${rows.filter((record) => record.request_attempted).length}; retries: 0; candidate prompt: none.`,
    `Cost: unavailable (no applicable verified rate recorded).`, '',
    ...(runs.length === 0 ? ['Live provider blocker: `.env` has placeholder model/key values, the current shell has no NVIDIA variables, and the local Docker daemon was inaccessible. No NVIDIA inference-specific connected tool was available. The CLI stopped before sending an HTTP request; historical diagnostics were not treated as current access.', ''] : []),
    'The measured semantic score covers only exact service/urgency and conservative location/time grading plus a narrow deterministic prohibited-claim guard. Every summary requires human review and is excluded from automatic semantic-accuracy claims. Provider/schema failures remain in attempted-case denominators.', '',
    reportSection('Development baseline (selection split)', dev?.records ?? [], Object.keys(categoryCounts)),
    reportSection('Held-out baseline (evaluation split)', held?.records ?? [], Object.keys(categoryCounts)),
    '## Representative failures', ''
  ];
  const failures = rows.filter((record) => record.outcome !== 'usable_output' || !record.grading.automatic_semantic_correct).slice(0, 8);
  if (!failures.length) lines.push('No retained provider responses to inspect yet.');
  else for (const item of failures) {
    const source = dataset.cases.find((candidate) => candidate.id === item.case_id);
    lines.push(`- **${item.case_id} (${item.outcome})**: ${(source?.rationale ?? 'synthetic case').replace(/[.\s]+$/, '')}; expected ${JSON.stringify(source?.expected)}; extracted ${JSON.stringify(item.extracted)}; field results ${JSON.stringify(item.grading.field_results)}${item.error_class ? `; safe error class \`${item.error_class}\`` : ''}.`);
  }
  lines.push('', '## Dataset and label limitations', '',
    'All examples are hand-authored synthetic enquiries. Labels encode the explicit v1 rubric and are not independent human ground truth; there was an independent AI-assisted rubric review, not a human validation study. The urgency convention is only for repeatable portfolio evaluation and is not a clinical or professionally validated safety policy. Location/time normalization intentionally avoids guessing aliases, relative dates, or time zones.', '',
    'Scoring caveat from development case S004: the input explicitly says “Richmond office,” while the canonical location label is “Richmond.” The extracted location preserves that source-supported specificity, but the conservative exact normalized matcher marks it incorrect. The label was not changed after evaluation; this is a known automatic-scoring false-negative risk and needs operator review.', '',
    'Category counts (development / held out): ' + Object.entries(categoryCounts).map(([category, counts]) => `${category} ${counts.development}/${counts.held_out}`).join('; ') + '.', '',
    '## Limitations and next step', '',
    'No candidate prompt was created or selected: only 13/40 development cases were attempted and just 6 usable outputs remain, which is too little evidence to distinguish a repeatable prompt defect from sampling noise. The 20 held-out cases were not sent.', '',
    'No production accuracy, customer ROI, or human validation is claimed. The narrow automatic claim guard can miss unsupported prose; the review-marked summaries must be checked by an operator. Milestone 2B should add an audited operator review/correction workflow that captures original model output, accepted corrections, reviewer identity/time, and a versioned reason without allowing model output to confirm bookings or invent facts.', '',
    'Reproduction commands: `node scripts/ai-evaluation.mjs validate`; `npm run test:evaluation`; `bash scripts/ai-evaluation-via-n8n.sh run --split development --run-id baseline-development`; after development selection, `bash scripts/ai-evaluation-via-n8n.sh run --split held_out --run-id baseline-held-out`; then `node scripts/ai-evaluation.mjs report`.', ''
  );
  fs.mkdirSync(path.join(ROOT, 'docs/reviews'), { recursive: true });
  fs.writeFileSync(path.join(ROOT, 'docs/reviews/milestone-2a-results.md'), lines.join('\n'));
  process.stdout.write('Wrote docs/reviews/milestone-2a-results.md\n');
}

function validateCommand() {
  const datasetText = read(DATASET_PATH);
  const dataset = JSON.parse(datasetText);
  const rubric = JSON.parse(read(RUBRIC_PATH));
  const issues = validateDataset(dataset, rubric);
  const contract = readContract();
  if (issues.length) throw new Error(issues.join('\n'));
  process.stdout.write(`Valid dataset: ${dataset.cases.length} cases, ${dataset.cases.filter((x) => x.split === 'development').length} development, ${dataset.cases.filter((x) => x.split === 'held_out').length} held out\n`);
  process.stdout.write(`dataset sha256 ${sha256(datasetText)}\nrubric sha256 ${sha256(read(RUBRIC_PATH))}\nprompt sha256 ${contract.promptHash}\ncontract sha256 ${contract.contractHash}\n`);
}

export {
  assertRunCompatible,
  gradeCase,
  loadLedger,
  pendingCases,
  readContract,
  runExportedValidator,
  summarize,
  validateDataset
};

const [command, ...args] = process.argv.slice(2);
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) try {
  if (command === 'validate') validateCommand();
  else if (command === 'run') {
    const split = args[args.indexOf('--split') + 1];
    const runId = args[args.indexOf('--run-id') + 1];
    if (!['development', 'held_out'].includes(split) || !runId || !/^[a-z0-9-]+$/.test(runId)) throw new Error('Usage: run --split development|held_out --run-id baseline-development|baseline-held-out');
    await runLive(split, runId);
  } else if (command === 'report') generateReport();
  else throw new Error('Commands: validate | run --split development|held_out --run-id ID | report');
} catch (error) {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = error?.safeCode === 'configuration_unavailable' ? 3 : 1;
}
