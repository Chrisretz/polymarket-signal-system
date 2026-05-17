#!/bin/sh
set -e

# Railway sætter PORT automatisk på web/worker-services
echo "PSS: PORT=${PORT:-(ikke sat — health-server bruger 8080 internt)}"

echo "PSS: kører database-migrationer..."
uv run python scripts/init_db.py

echo "PSS: starter scheduler..."
exec uv run python -m pss.scheduler
