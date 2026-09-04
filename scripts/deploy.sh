#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required." >&2
  exit 1
fi

if [ ! -f .env ]; then
  echo "Missing .env. Copy .env.example to .env and review every setting before deployment." >&2
  exit 1
fi

docker compose build --pull
docker compose up -d --remove-orphans
docker compose ps
curl --fail --silent --show-error http://localhost:8000/health >/dev/null
echo "Deployment smoke check passed."
