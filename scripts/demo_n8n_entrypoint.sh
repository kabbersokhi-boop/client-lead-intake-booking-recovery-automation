#!/bin/sh
set -eu

marker=/home/node/.n8n/.guided-demo-imported
if [ ! -f "$marker" ]; then
  n8n import:workflow --separate --input=/demo/workflows
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
  touch "$marker"
fi

exec n8n start
