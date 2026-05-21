"""Polymarket CLOB API (read-only: prishistorik)."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

CLOB_BASE_URL = "https://clob.polymarket.com"


class ClobClient:
    """Minimal klient til /prices-history (ingen auth)."""

    def __init__(self, timeout: float = 60.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=CLOB_BASE_URL,
            timeout=timeout,
            headers={"User-Agent": "polymarket-signal-system/0.1"},
        )
        self._semaphore = asyncio.Semaphore(3)
        self._last_request_at: float = 0.0
        self._min_interval = 0.35

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> ClobClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        async with self._semaphore:
            now = time.monotonic()
            elapsed = now - self._last_request_at
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            response = await self._client.get(path, params=params)
            response.raise_for_status()
            self._last_request_at = time.monotonic()
            return response.json()

    async def fetch_prices_history(
        self,
        token_id: str,
        *,
        interval: str = "max",
        fidelity_minutes: int = 360,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> list[tuple[datetime, float]]:
        """Hent YES-token prishistorik. Returnerer (utc_dt, price)."""
        params: dict[str, Any] = {
            "market": token_id,
            "interval": interval,
            "fidelity": fidelity_minutes,
        }
        if start_ts is not None:
            params["startTs"] = start_ts
        if end_ts is not None:
            params["endTs"] = end_ts

        try:
            payload = await self._get("/prices-history", params)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "clob_prices_history_error",
                token_id=token_id[:16],
                status=exc.response.status_code,
                body=exc.response.text[:120],
            )
            return []

        history = payload.get("history", []) if isinstance(payload, dict) else []
        points: list[tuple[datetime, float]] = []
        for row in history:
            try:
                ts = int(row["t"])
                price = float(row["p"])
            except (KeyError, TypeError, ValueError):
                continue
            points.append((datetime.fromtimestamp(ts, tz=timezone.utc), price))

        points.sort(key=lambda x: x[0])
        return points
