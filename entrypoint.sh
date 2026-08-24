#!/bin/sh
set -eu

cd "$(dirname "$0")"

exec python -m uvicorn backend.app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}"
