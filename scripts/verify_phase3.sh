#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
container="phase3-verify-postgres-$$"
database_user=phase3_verify
database_password=phase3_verify_password
database_name=phase3_verify

cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

cd "$repo_dir"
docker run -d --name "$container" \
  -e POSTGRES_USER="$database_user" \
  -e POSTGRES_PASSWORD="$database_password" \
  -e POSTGRES_DB="$database_name" \
  -p 127.0.0.1::5432 postgres:16-alpine >/dev/null

for _ in $(seq 1 30); do
  if docker exec "$container" pg_isready -U "$database_user" -d "$database_name" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "$container" pg_isready -U "$database_user" -d "$database_name" >/dev/null
database_port=$(docker port "$container" 5432/tcp | sed 's/.*://')
export TEST_POSTGRES_URL="postgresql+psycopg://${database_user}:${database_password}@127.0.0.1:${database_port}/${database_name}"

echo "[phase3] Python/PostgreSQL tests (pytest discovers backend/tests)"
.venv/bin/python -m pytest -q -ra backend/tests

echo "[phase3] Python lint"
.venv/bin/ruff check backend/app backend/simulator backend/tests scripts/phase3_demo.py

echo "[phase3] Browser tests (Node wildcard discovery)"
npm run test:browser

echo "[phase3] Workflow-code tests (Node wildcard discovery)"
npm run test:workflow

echo "[phase3] Simulator JavaScript syntax"
node --check backend/simulator/static/app.js

echo "[phase3] JSON, shell, Compose, and diff checks"
.venv/bin/python - <<'PY'
import json
from pathlib import Path

for path in [*Path("n8n").glob("*.json"), *Path("docs/fixtures").glob("*.json")]:
    json.loads(path.read_text())
PY
bash -n scripts/verify_phase3.sh
docker compose config --quiet
git diff --check

echo "[phase3] Tracked-content secret scan"
if git grep -nEI 'nvapi-[A-Za-z0-9_-]+|Bearer[[:space:]]+[A-Za-z0-9_-]{20,}|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY' -- . ':!docs/phase-1-verification.md'; then
  echo "Potential secret material found in tracked content" >&2
  exit 1
fi

echo "[phase3] PASS: deterministic checks completed with disposable PostgreSQL"
echo "[phase3] SKIPPED HERE: live n8n/NVIDIA/Mailpit fault scenarios require the preserved local runtime"
echo "[phase3] See docs/phase-3-verification.md for the separately executed live evidence"
