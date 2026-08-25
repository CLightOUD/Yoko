#!/bin/sh
set -eu

cd "$(dirname "$0")"

exec python -m uvicorn backend.app.main:app \
  --host "${APP_HOST:-0.0.0.0}" \
  --port "${PORT:-${APP_PORT:-8000}}"
