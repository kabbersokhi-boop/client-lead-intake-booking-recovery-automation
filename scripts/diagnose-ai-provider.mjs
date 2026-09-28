// Synthetic transport diagnostics, separate from frozen evaluation results.
import fs from 'node:fs';
import https from 'node:https';
import crypto from 'node:crypto';
import path from 'node:path';
import { readContract, runExportedValidator } from './ai-evaluation.mjs';

const transport = process.argv[2] || 'https';
const timeoutMs = Number(process.argv[3] || 45000);
const minimal = process.argv[4] === 'minimal';
const lightning = process.argv[4] === 'lightning';
if (!['https', 'fetch'].includes(transport) || !Number.isInteger(timeoutMs)
    || timeoutMs < 1000 || timeoutMs > 60000) throw new Error('Invalid diagnostic options');
const key = process.env.NVIDIA_NIM_API_KEY;
if (!key) throw new Error('Runtime NVIDIA credential required');
const contract = readContract();
const endpoint = new URL(process.env.AI_PROVIDER_URL || contract.settings.default_endpoint);
if (endpoint.origin !== 'https://integrate.api.nvidia.com') throw new Error('Official NVIDIA endpoint required');
const file = process.env.AI_DIAGNOSTIC_LEDGER;
if (!file) throw new Error('AI_DIAGNOSTIC_LEDGER required');
if (path.basename(file) !== 'provider-diagnostics.jsonl') throw new Error('Use provider-diagnostics.jsonl for shared request accounting');
process.env.AI_EVAL_RUN_DIR=path.dirname(path.resolve(file));
const {acquireLock,loadRequestBudget,assertRequestBudget}=await import('./ai-evaluation-v2.mjs');
const unlock=acquireLock(path.join(process.env.AI_EVAL_RUN_DIR,'.milestone-2a-v2.lock'));
try {
assertRequestBudget(loadRequestBudget());
const requestId = crypto.randomUUID();
function record(data) {
  const fd = fs.openSync(file, 'a', 0o600);
  try { fs.writeSync(fd, JSON.stringify({request_id: requestId, ...data}) + '\n'); fs.fsyncSync(fd); }
  finally { fs.closeSync(fd); }
}
const body = JSON.stringify(minimal ? {
  model:process.env.NVIDIA_NIM_MODEL,max_tokens:32,
  messages:[{role:'user',content:'Reply with just OK.'}],
} : {
  model: process.env.NVIDIA_NIM_MODEL,
  temperature: contract.settings.temperature, max_tokens: contract.settings.max_tokens,
  ...(lightning ? {reasoning_budget:0,stream:false,max_tokens:512} : {reasoning_effort:contract.settings.reasoning_effort}),
  response_format: contract.settings.response_format,
  messages: [{role:'system',content:contract.prompt},
    {role:'user',content:'My furnace stopped heating in Surrey. Can someone come Tuesday afternoon?'}],
});
record({kind:'reservation', diagnostic:true, transport, minimal, lightning, timeout_ms:timeoutMs,
  model:process.env.NVIDIA_NIM_MODEL, contract_hash:contract.contractHash,
  reserved_at:new Date().toISOString()});
const start = performance.now();
const timings = {};
try {
  let status, raw;
  if (transport === 'fetch') {
    const response = await fetch(endpoint, {method:'POST',
      headers:{authorization:`Bearer ${key}`,'content-type':'application/json'},body,
      signal:AbortSignal.timeout(timeoutMs)});
    timings.headers_ms = Math.round(performance.now()-start);
    status=response.status; raw=await response.text();
  } else {
    ({status,raw} = await new Promise((resolve,reject)=>{
      const req=https.request(endpoint,{method:'POST',headers:{authorization:`Bearer ${key}`,
        'content-type':'application/json','content-length':Buffer.byteLength(body)}},res=>{
        timings.headers_ms=Math.round(performance.now()-start);
        const chunks=[]; res.on('data',c=>chunks.push(c));
        res.on('error',reject);res.on('end',()=>resolve({status:res.statusCode,raw:Buffer.concat(chunks).toString()}));
      });
      req.on('socket',socket=>{
        socket.on('lookup',()=>{timings.dns_ms=Math.round(performance.now()-start);});
        socket.on('connect',()=>{timings.tcp_ms=Math.round(performance.now()-start);});
        socket.on('secureConnect',()=>{timings.tls_ms=Math.round(performance.now()-start);});
      });
      const timer=setTimeout(()=>req.destroy(Object.assign(new Error('deadline'),{code:'DIAGNOSTIC_TIMEOUT'})),timeoutMs);
      req.on('close',()=>clearTimeout(timer));req.on('error',reject);req.end(body);
    }));
  }
  let response;try{response=JSON.parse(raw);}catch{response=null;}
  const content=response?.choices?.[0]?.message?.content;
  const validated=response?runExportedValidator(contract,response,'Synthetic diagnostic'):null;
  const result={kind:'settlement',transport,status,elapsed_ms:Math.round(performance.now()-start),
    timings,finish_reason:response?.choices?.[0]?.finish_reason??null,
    content_present:typeof content==='string'&&content.length>0,
    schema_valid:validated?.ai_status==='enriched',extracted:validated?.enrichment??null,
    usage:response?.usage??null};
  record(result);console.log(JSON.stringify(result));
} catch(error) {
  const result={kind:'settlement',transport,status:null,elapsed_ms:Math.round(performance.now()-start),
    timings,error_class:error.name,error_code:error.code??error.cause?.code??null};
  record(result);console.log(JSON.stringify(result));process.exitCode=1;
}
} finally { unlock(); }
