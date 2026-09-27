#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
container=${AI_EVALUATION_N8N_CONTAINER:-n8n}
remote_root=/tmp/milestone-2a-ai-evaluation
remote_runs=/home/node/.n8n/ai-evaluation-runs
run_id=
for ((index = 1; index <= $#; index += 1)); do
  if [[ ${!index} == "--run-id" ]]; then
    next=$((index + 1))
    run_id=${!next-}
    break
  fi
done

if [[ ${1-} != "run" || ! $run_id =~ ^baseline-(development|held-out)$ ]]; then
  echo "Usage: bash scripts/ai-evaluation-via-n8n.sh run --split development|held_out --run-id baseline-development|baseline-held-out" >&2
  exit 2
fi

local_runs="$repo_dir/docs/reviews/ai-evaluation-runs"
local_ledger="$local_runs/$run_id.jsonl"
remote_ledger="$remote_runs/$run_id.jsonl"

docker exec "$container" mkdir -p \
  "$remote_root/scripts" "$remote_root/n8n/evaluation" "$remote_root/n8n" "$remote_runs"
docker cp "$repo_dir/scripts/ai-evaluation.mjs" "$container:$remote_root/scripts/ai-evaluation.mjs"
docker cp "$repo_dir/n8n/lead-intake.json" "$container:$remote_root/n8n/lead-intake.json"
docker cp "$repo_dir/n8n/evaluation/dataset-v1.json" "$container:$remote_root/n8n/evaluation/dataset-v1.json"
docker cp "$repo_dir/n8n/evaluation/rubric-v1.json" "$container:$remote_root/n8n/evaluation/rubric-v1.json"

if [[ ! -e $local_ledger ]] && ! docker exec "$container" test -f "$remote_ledger"; then
  :
elif ! docker exec "$container" test -f "$remote_ledger"; then
  docker cp "$local_ledger" "$container:$remote_ledger"
fi

docker exec -e "AI_EVAL_RUN_DIR=$remote_runs" "$container" \
  node "$remote_root/scripts/ai-evaluation.mjs" "$@"

mkdir -p "$local_runs"
docker cp "$container:$remote_ledger" "$local_ledger"
