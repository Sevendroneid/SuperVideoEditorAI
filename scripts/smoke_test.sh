#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"

curl --fail --silent --show-error "${API_URL}/health" >/dev/null
PROJECT_JSON="$(curl --fail --silent --show-error -X POST "${API_URL}/api/v1/projects")"
PROJECT_ID="$(python -c 'import json,sys; print(json.load(sys.stdin)["project_id"])' <<<"${PROJECT_JSON}")"

case "${PROJECT_ID}" in
  (*[!a-zA-Z0-9_-]*|'') echo "Invalid project id returned" >&2; exit 1;;
esac

echo "API smoke test passed. Project: ${PROJECT_ID}"
