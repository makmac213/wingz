#!/bin/bash
# ---------------------------------------------------------------------------
# Container entrypoint: ensure the schema and demo data exist, then hand off
# to the CMD (gunicorn). Runs on every fresh container start.
# ---------------------------------------------------------------------------
set -e

echo "[entrypoint] Applying database migrations..."
python manage.py migrate --noinput

echo "[entrypoint] Seeding demo data..."
python manage.py seed_data

echo "[entrypoint] Starting application: $*"
exec "$@"
