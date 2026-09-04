#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required." >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

mkdir -p storage/uploads storage/projects storage/outputs
docker compose build
docker compose up -d
docker compose ps
printf '\nDashboard: http://localhost:3000\nAPI: http://localhost:8000/docs\nHealth: http://localhost:8000/health\n'
