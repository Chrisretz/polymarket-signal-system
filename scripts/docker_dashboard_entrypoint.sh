#!/bin/sh
set -e

PORT="${PORT:-8501}"
echo "========================================"
echo "PSS STREAMLIT DASHBOARD (ikke scheduler)"
echo "PORT=${PORT}"
echo "========================================"

exec uv run streamlit run src/pss/dashboard/app.py \
  --server.port="${PORT}" \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --browser.gatherUsageStats=false
