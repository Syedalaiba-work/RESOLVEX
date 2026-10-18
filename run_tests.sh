#!/usr/bin/env sh
# Runs the backend unit/integration tests inside Docker (only Docker is required on the host).
# Usage: ./run_tests.sh            -> tests + per-area coverage summary
set -eu
cd "$(dirname "$0")"

export DAY1_SALT="${DAY1_SALT:-test-salt}"
export MSYS_NO_PATHCONV=1  # Git Bash on Windows: keep container paths like /tmp untouched
docker compose up -d --build db api
docker compose exec -T api python -m pytest -q --cov=backend/app --cov-config=.coveragerc \
  --cov-report=term --cov-report=json:/tmp/coverage.json "$@"
docker compose exec -T api python backend/tools/coverage_by_area.py /tmp/coverage.json
docker compose exec -T api python backend/tools/coverage_by_area.py /tmp/coverage.json --day2
