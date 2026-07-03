#!/usr/bin/env bash
set -euo pipefail
cd /Users/vicki/service/1052
set -a
if [ -f .env ]; then
  source .env
fi
set +a
exec .venv/bin/python server.py
