"""Minimal HTTP-server til Railway healthcheck (scheduler har ellers ingen port)."""

from __future__ import annotations

import asyncio
import os

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_HEALTH_PORT = 8080


def resolve_health_port() -> int:
    """Port til healthcheck — Railway sætter PORT; ellers 8080 i prod/Docker."""
    raw = os.environ.get("PORT")
    if raw:
        return int(raw)
    return DEFAULT_HEALTH_PORT


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    try:
        await reader.readline()
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break
        body = b"ok"
        writer.write(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/plain\r\n"
            b"Content-Length: 2\r\n"
            b"Connection: close\r\n\r\n" + body,
        )
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def run_health_server(port: int) -> None:
    server = await asyncio.start_server(_handle_client, "0.0.0.0", port)
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets or [])
    logger.info("health_server_listening", port=port, addrs=addrs)
    print(f"PSS: health-server lytter på 0.0.0.0:{port}", flush=True)
    async with server:
        await server.serve_forever()


def start_health_server_task() -> asyncio.Task[None]:
    """Start health-server (altid — Railway healthcheck kræver HTTP på PORT)."""
    port = resolve_health_port()
    return asyncio.create_task(run_health_server(port))
