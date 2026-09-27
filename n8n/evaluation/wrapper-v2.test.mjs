import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const runId = 'baseline-v2-development';
const runArgs = ['scripts/ai-evaluation-via-n8n.sh', 'run', '--split', 'development', '--run-id', runId];

function fixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-eval-wrapper-'));
  const repo = path.join(root, 'repo');
  const bin = path.join(root, 'bin');
  const remote = path.join(root, 'remote');
  fs.mkdirSync(path.join(repo, 'scripts'), { recursive: true });
  fs.mkdirSync(path.join(repo, 'n8n/evaluation'), { recursive: true });
  fs.mkdirSync(path.join(repo, 'n8n'), { recursive: true });
  fs.mkdirSync(bin);
  for (const file of [
    'scripts/ai-evaluation-via-n8n.sh', 'scripts/ai-evaluation.mjs', 'scripts/ai-evaluation-v2.mjs',
    'n8n/lead-intake.json', 'n8n/evaluation/dataset-v1.json',
    'n8n/evaluation/dataset-v2-revision.json', 'n8n/evaluation/rubric-v2.json'
  ]) fs.copyFileSync(path.join(ROOT, file), path.join(repo, file));
  const dockerMock = `#!/usr/bin/env node
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const a=process.argv.slice(2), base=process.env.FAKE_REMOTE;
function map(p){if(p==='/home/node/.n8n/ai-evaluation-runs'||p.startsWith('/home/node/.n8n/ai-evaluation-runs/'))return p.endsWith('/ai-evaluation-runs')?path.join(base,'runs'):path.join(base,'runs',path.basename(p));if(p==='/tmp/milestone-2a-ai-evaluation'||p.startsWith('/tmp/milestone-2a-ai-evaluation/'))return p.endsWith('/milestone-2a-ai-evaluation')?path.join(base,'stage'):path.join(base,'stage',p.slice('/tmp/milestone-2a-ai-evaluation/'.length));throw Error('unexpected path '+p)}
function mkdirFor(p){fs.mkdirSync(path.dirname(p),{recursive:true})}
if(a[0]==='cp'){let src=a[1],dst=a[2];if(src.startsWith('n8n:')){src=map(src.slice(4));dst=dst}else if(dst.startsWith('n8n:')){dst=map(dst.slice(4))}else throw Error('bad cp');mkdirFor(dst);fs.copyFileSync(src,dst);process.exit(0)}
if(a[0]!=='exec')throw Error('unsupported docker command');
let i=1;if(a[i]==='-e')i+=2;i++;const cmd=a[i++];
if(cmd==='mkdir'){for(const p of a.slice(i).filter(x=>!x.startsWith('-'))){fs.mkdirSync(map(p),{recursive:true})}process.exit(0)}
if(cmd==='test'){process.exit(fs.existsSync(map(a[i+1]))?0:1)}
if(cmd==='sha256sum'){const p=map(a[i]);console.log(crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex')+'  '+a[i]);process.exit(0)}
if(cmd==='node'){const ledger=path.join(base,'runs',${JSON.stringify(runId)}+'.jsonl');fs.mkdirSync(path.dirname(ledger),{recursive:true});fs.appendFileSync(ledger,'fake retained provider evidence\\n');process.exit(Number(process.env.FAKE_NODE_STATUS||0))}
throw Error('unsupported docker exec command '+cmd);
`;
  fs.writeFileSync(path.join(bin, 'docker'), dockerMock, { mode: 0o755 });
  return { root, repo, bin, remote };
}

function execute(f, extra = {}) {
  return spawnSync('bash', runArgs, {
    cwd: f.repo,
    encoding: 'utf8',
    env: { ...process.env, PATH: `${f.bin}:${process.env.PATH}`, FAKE_REMOTE: f.remote, ...extra }
  });
}

test('container runner copies retained ledger evidence back after provider command failure', () => {
  const f = fixture();
  try {
    const result = execute(f, { FAKE_NODE_STATUS: '9' });
    assert.equal(result.status, 9, result.stderr);
    const ledger = path.join(f.repo, 'docs/reviews/ai-evaluation-runs', `${runId}.jsonl`);
    assert.match(fs.readFileSync(ledger, 'utf8'), /fake retained provider evidence/);
  } finally { fs.rmSync(f.root, { recursive: true, force: true }); }
});

test('container runner refuses divergent local and remote ledgers without replacing either', () => {
  const f = fixture();
  try {
    const local = path.join(f.repo, 'docs/reviews/ai-evaluation-runs', `${runId}.jsonl`);
    const remote = path.join(f.remote, 'runs', `${runId}.jsonl`);
    fs.mkdirSync(path.dirname(local), { recursive: true });
    fs.mkdirSync(path.dirname(remote), { recursive: true });
    fs.writeFileSync(local, 'local evidence\n');
    fs.writeFileSync(remote, 'remote evidence\n');
    const result = execute(f);
    assert.equal(result.status, 4);
    assert.match(fs.readFileSync(local, 'utf8'), /local evidence/);
    assert.match(fs.readFileSync(remote, 'utf8'), /remote evidence/);
  } finally { fs.rmSync(f.root, { recursive: true, force: true }); }
});
