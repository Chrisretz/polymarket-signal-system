#!/bin/sh
set -e

echo "PSS: kører database-migrationer..."
uv run python scripts/init_db.py

echo "PSS: starter scheduler..."
exec uv run python -m pss.scheduler
