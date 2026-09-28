import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {readContract} from '../../scripts/ai-evaluation.mjs';
import {evaluationProfile, makeManifest, loadDataset} from '../../scripts/ai-evaluation-v2.mjs';
import {lightningWorkflow} from '../../scripts/export-lightning-workflow.mjs';

test('opt-in workflow sends exactly the evaluated settings and preserves baseline/fallback',()=>{
  const contract=readContract(); const before=JSON.stringify(contract.workflow);
  const profile=evaluationProfile('lightning',{},contract);
  const exported=lightningWorkflow(contract.workflow,profile);
  const nodes=Object.fromEntries(exported.nodes.map(n=>[n.name,n]));
  const expression=nodes['Extract Service Context with NVIDIA NIM'].parameters.jsonBody;
  const body=vm.runInNewContext(`(${expression.slice(3,-2)})`,{
    $env:{NVIDIA_NIM_MODEL:'old-model'},
    $:()=>({first:()=>({json:{lead:{normalized_message:'test synthetic request'}}})}),
  });
  assert.equal(body.model,profile.model);
  for(const [key,value] of Object.entries(profile.inference_settings))assert.equal(JSON.stringify(body[key]),JSON.stringify(value));
  assert.equal(body.reasoning_effort,undefined);
  assert.match(nodes['Validate AI Extraction'].parameters.jsCode,/fallback_unavailable/);
  assert.match(nodes['Validate AI Extraction'].parameters.jsCode,/nvidia\/nemotron-3.5-lightning/);
  assert.equal(JSON.stringify(contract.workflow),before);
  const args={provider:'nvidia_nim',endpoint:'https://integrate.api.nvidia.com/v1/chat/completions',
    timeoutMs:18000,datasetHash:loadDataset().datasetHash,rubricHash:'test',contract};
  const legacy=evaluationProfile('baseline',{model:'openai/gpt-oss-20b',timeout:18000},contract);
  assert.notEqual(makeManifest({...args,model:legacy.model,settings:legacy.inference_settings}).experiment_id,
    makeManifest({...args,model:profile.model,settings:profile.inference_settings}).experiment_id);
});

test('shared budget charges legacy floor, both profiles and unsettled diagnostic reservations',()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'ai-budget-'));
  try {
    for(const name of ['baseline-v2-development.jsonl','lightning-v2-development.jsonl','provider-diagnostics.jsonl']) {
      fs.writeFileSync(path.join(dir,name),JSON.stringify({kind:'reservation'})+'\n');
    }
    const moduleUrl=new URL('../../scripts/ai-evaluation-v2.mjs',import.meta.url).href;
    const result=spawnSync(process.execPath,['--input-type=module','-e',
      `import {loadRequestBudget} from ${JSON.stringify(moduleUrl)}; console.log(loadRequestBudget());`],
      {env:{...process.env,AI_EVAL_RUN_DIR:dir},encoding:'utf8'});
    assert.equal(result.status,0,result.stderr);
    assert.equal(result.stdout.trim(),'16');
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
});
