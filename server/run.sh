#!/bin/bash
cd "$(dirname "$0")"
export DATABASE_URL="${DATABASE_URL:-postgresql://neondb_owner:npg_test@127.0.0.1:5435/neondb}"
export DB_SSL="${DB_SSL:-disable}"
exec .venv/bin/uvicorn main:socket_app --host 0.0.0.0 --port 8000 >> /tmp/axiom-server.log 2>&1