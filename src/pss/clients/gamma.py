"""Wrapper for Polymarket Gamma API (read-only markedsdata)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
# Gamma returnerer 422 når offset + limit overstiger ~10k indexeret
GAMMA_MAX_MARKET_OFFSET = 10_000


class GammaClient:
    """Async wrapper for Polymarket Gamma API.

    Rate limit: cirka 60 req/min uden auth. Vi holder os godt under.
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=GAMMA_BASE_URL,
            timeout=timeout,
            headers={"User-Agent": "polymarket-signal-system/0.1"},
        )
        self._semaphore = asyncio.Semaphore(5)
        self._last_request_at: float = 0.0
        self._min_interval = 2.0

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> GammaClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        async with self._semaphore:
            now = time.monotonic()
            elapsed = now - self._last_request_at
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)

            try:
                response = await self._client.get(path, params=params)
                response.raise_for_status()
                self._last_request_at = time.monotonic()
                return response.json()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status == 422 and path == "/markets":
                    logger.warning(
                        "gamma_pagination_limit_reached",
                        offset=(params or {}).get("offset"),
                        body=exc.response.text[:120],
                    )
                    return []
                logger.error(
                    "gamma_api_error",
                    path=path,
                    status=status,
                    body=exc.response.text[:200],
                )
                raise

    async def list_markets(
        self,
        *,
        active: bool = True,
        closed: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Henter liste af markeder med pagination."""
        if offset >= GAMMA_MAX_MARKET_OFFSET:
            logger.warning("gamma_pagination_limit_reached", offset=offset, reason="cap")
            return []

        params = {
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "limit": limit,
            "offset": offset,
        }
        data = await self._get("/markets", params=params)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("data", []) or []
        return []

    async def get_market(self, condition_id: str) -> dict[str, Any]:
        """Henter detaljer for ét specifikt marked."""
        result = await self._get(f"/markets/{condition_id}")
        if isinstance(result, dict):
            return result
        return {}

    async def iter_active_market_pages(
        self,
        *,
        page_size: int = 100,
    ):
        """Yield batches af aktive markeder; stop før Gamma offset-grænse."""
        offset = 0
        while offset < GAMMA_MAX_MARKET_OFFSET:
            batch = await self.list_markets(
                active=True,
                closed=False,
                limit=page_size,
                offset=offset,
            )

            if not batch:
                break
            yield batch
            if len(batch) < page_size:
                break
            offset += page_size
        else:
            logger.warning(
                "gamma_pagination_limit_reached",
                offset=offset,
                reason="max_offset_cap",
            )

    async def list_all_active_markets(self) -> list[dict[str, Any]]:
        """Henter aktive markeder via pagination (max ~10k via offset)."""
        all_markets: list[dict[str, Any]] = []
        async for batch in self.iter_active_market_pages():
            all_markets.extend(batch)
        logger.info("fetched_active_markets", count=len(all_markets))
        return all_markets

    async def list_events(
        self,
        *,
        active: bool = True,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Henter events (grupper af relaterede markeder)."""
        params = {
            "active": str(active).lower(),
            "limit": limit,
        }
        data = await self._get("/events", params=params)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("data", []) or []
        return []
