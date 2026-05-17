#!/bin/bash
set -e
cd "$(dirname "$0")"
source .env 2>/dev/null || true
# Bind to localhost only; remote browser access is through Tailscale Serve.
exec caffeinate -i uvicorn backend.main:app --host 127.0.0.1 --port 8080
