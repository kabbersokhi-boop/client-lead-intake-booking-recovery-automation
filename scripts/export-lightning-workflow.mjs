// Generate a deployable opt-in workflow without rewriting the frozen baseline.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
export function lightningWorkflow(workflow, profile) {
  const result=structuredClone(workflow);
  const request=result.nodes.find(n=>n.name==='Extract Service Context with NVIDIA NIM');
  const validator=result.nodes.find(n=>n.name==='Validate AI Extraction');
  if (!request || !validator) throw new Error('Baseline extraction nodes missing');
  const replacements=[
    ['model: $env.NVIDIA_NIM_MODEL',`model: ${JSON.stringify(profile.model)}`],
    ['max_tokens: 180',`max_tokens: ${profile.inference_settings.max_tokens}`],
    ["reasoning_effort: 'low'",`reasoning_budget: ${profile.inference_settings.reasoning_budget}, stream: false`],
  ];
  for(const [before,after] of replacements){
    if(!request.parameters.jsonBody.includes(before))throw new Error('Baseline request changed; inspect profile compatibility');
    request.parameters.jsonBody=request.parameters.jsonBody.replace(before,after);
  }
  validator.parameters.jsCode=validator.parameters.jsCode.replaceAll('$env.NVIDIA_NIM_MODEL',JSON.stringify(profile.model));
  return result;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const workflow=JSON.parse(fs.readFileSync(path.join(root,'n8n/lead-intake.json'),'utf8'));
  const profile=JSON.parse(fs.readFileSync(path.join(root,'n8n/evaluation/lightning-profile.json'),'utf8'));
  process.stdout.write(JSON.stringify(lightningWorkflow(workflow,profile),null,2)+'\n');
}
