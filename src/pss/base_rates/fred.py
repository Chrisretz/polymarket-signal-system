"""FRED API (historiske makro-serier)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

FRED_API_BASE = "https://api.stlouisfed.org/fred"


class FredClient:
    """Minimal async klient til series/observations."""

    def __init__(self, api_key: str, *, timeout: float = 60.0) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=FRED_API_BASE,
            timeout=timeout,
            headers={"User-Agent": "pss/0.1"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> FredClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def fetch_observations(
        self,
        series_id: str,
        *,
        observation_start: str = "1990-01-01",
    ) -> list[tuple[date, float]]:
        params = {
            "series_id": series_id,
            "api_key": self._api_key,
            "file_type": "json",
            "observation_start": observation_start,
        }
        resp = await self._client.get("/series/observations", params=params)
        resp.raise_for_status()
        payload = resp.json()
        points: list[tuple[date, float]] = []
        for row in payload.get("observations", []):
            raw = row.get("value")
            if raw in (None, "."):
                continue
            try:
                value = float(raw)
            except ValueError:
                continue
            obs_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
            points.append((obs_date, value))
        logger.info("fred_observations_fetched", series_id=series_id, count=len(points))
        return points
