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

if [[ ${1-} != "run" || ! $run_id =~ ^baseline-v2-(development|held_out)$ ]]; then
  echo "Usage: bash scripts/ai-evaluation-via-n8n.sh run --split development|held_out --run-id baseline-v2-development|baseline-v2-held_out" >&2
  exit 2
fi

local_runs="$repo_dir/docs/reviews/ai-evaluation-runs"
local_ledger="$local_runs/$run_id.jsonl"
remote_ledger="$remote_runs/$run_id.jsonl"
remote_copy=$(mktemp "${TMPDIR:-/tmp}/ai-eval-ledger.XXXXXX")
trap 'rm -f "$remote_copy"' EXIT

docker exec "$container" mkdir -p \
  "$remote_root/scripts" "$remote_root/n8n/evaluation" "$remote_root/n8n" "$remote_runs"
docker cp "$repo_dir/scripts/ai-evaluation.mjs" "$container:$remote_root/scripts/ai-evaluation.mjs"
docker cp "$repo_dir/scripts/ai-evaluation-v2.mjs" "$container:$remote_root/scripts/ai-evaluation-v2.mjs"
docker cp "$repo_dir/n8n/lead-intake.json" "$container:$remote_root/n8n/lead-intake.json"
docker cp "$repo_dir/n8n/evaluation/dataset-v1.json" "$container:$remote_root/n8n/evaluation/dataset-v1.json"
docker cp "$repo_dir/n8n/evaluation/dataset-v2-revision.json" "$container:$remote_root/n8n/evaluation/dataset-v2-revision.json"
docker cp "$repo_dir/n8n/evaluation/rubric-v2.json" "$container:$remote_root/n8n/evaluation/rubric-v2.json"

local_before=
if [[ -e $local_ledger ]]; then
  local_before=$(sha256sum "$local_ledger" | cut -d ' ' -f 1)
fi
remote_exists=0
if docker exec "$container" test -f "$remote_ledger"; then remote_exists=1; fi
if [[ -e $local_ledger && $remote_exists == 1 ]]; then
  remote_before=$(docker exec "$container" sha256sum "$remote_ledger" | cut -d ' ' -f 1)
  if [[ $local_before != "$remote_before" ]]; then
    echo "Local and remote evaluation ledgers diverge; refusing to overwrite either copy." >&2
    exit 4
  fi
elif [[ -e $local_ledger ]]; then
  docker cp "$local_ledger" "$container:$remote_ledger"
fi

run_status=0
docker exec -e "AI_EVAL_RUN_DIR=$remote_runs" "$container" \
  node "$remote_root/scripts/ai-evaluation-v2.mjs" "$@" || run_status=$?

if docker exec "$container" test -f "$remote_ledger"; then
  docker cp "$container:$remote_ledger" "$remote_copy"
  if [[ -e $local_ledger ]]; then
    current_local=$(sha256sum "$local_ledger" | cut -d ' ' -f 1)
    if [[ $current_local != "$local_before" && $(sha256sum "$remote_copy" | cut -d ' ' -f 1) != "$current_local" ]]; then
      echo "Local ledger changed during container run; retained divergent local and remote evidence." >&2
      exit 5
    fi
  fi
  mkdir -p "$local_runs"
  mv "$remote_copy" "$local_ledger"
elif [[ $run_status == 0 ]]; then
  echo "Container run succeeded but expected persistent ledger is missing; local evidence was not overwritten." >&2
  exit 6
fi

exit "$run_status"
