#!/bin/bash
set -e
cd "$(dirname "$0")"
source .env 2>/dev/null || true
exec uvicorn backend.main:app --host 127.0.0.1 --port 8080 --reload
