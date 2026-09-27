#!/bin/sh
set -eu

marker=/home/node/.n8n/.guided-demo-imported
workflow_manifest="v2:$(sha256sum /demo/workflows/*.json | sha256sum | cut -d ' ' -f 1)"
installed_manifest=$(cat "$marker" 2>/dev/null || true)

if [ "$installed_manifest" != "$workflow_manifest" ]; then
  n8n import:workflow --separate --input=/demo/workflows
  printf '%s\n' "$workflow_manifest" > "$marker"
fi

for workflow_id in \
  GKMASmZ5xo0UaWUY \
  phase2-appointment-booking \
  phase2-follow-up-dispatch \
  phase3-crm-write-recovery \
  phase3-crm-recovery-error \
  phase7-highlevel-stage-sync
do
  n8n publish:workflow --id="$workflow_id"
done

exec n8n start
