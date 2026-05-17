#!/bin/sh
set -e

# Railway sætter PORT automatisk; fallback så healthcheck har et mål
if [ -z "${PORT:-}" ]; then
  export PORT=8080
  echo "PSS: PORT ikke sat af host — bruger PORT=8080"
else
  echo "PSS: PORT=$PORT"
fi

echo "PSS: kører database-migrationer..."
uv run python scripts/init_db.py

echo "PSS: starter scheduler..."
exec uv run python -m pss.scheduler
