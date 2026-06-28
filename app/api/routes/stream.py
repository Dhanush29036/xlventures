"""
app/api/routes/stream.py — Server-Sent Events (SSE) via Redis pub/sub.

The SSE endpoint subscribes to channel ``run:{run_id}:events`` and forwards
every message to the connected browser client.

A heartbeat comment (``: heartbeat\\n\\n``) is sent every 15 seconds to keep
the connection alive through proxies and load balancers.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis

from app.api.auth import get_current_tenant

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/stream", tags=["stream"])

HEARTBEAT_INTERVAL = 15  # seconds


async def _event_generator(
    run_id: str,
    redis_client: Redis,
    request: Request,
) -> AsyncIterator[str]:
    """
    Subscribe to the Redis pub/sub channel for this run and yield SSE frames.
    Sends a heartbeat every 15 s.  Stops when the client disconnects.
    """
    channel_name = f"run:{run_id}:events"
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel_name)
    logger.info("sse_subscribed", run_id=run_id, channel=channel_name)

    heartbeat_task: asyncio.Task | None = None

    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            yield  # trigger heartbeat send (handled in outer loop)

    try:
        last_heartbeat = asyncio.get_event_loop().time()
        while True:
            # Check client disconnect
            if await request.is_disconnected():
                logger.info("sse_client_disconnected", run_id=run_id)
                break

            # Non-blocking message poll
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

            if message and message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                yield f"data: {data}\n\n"

            # Heartbeat
            now = asyncio.get_event_loop().time()
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                yield ": heartbeat\n\n"
                last_heartbeat = now

            # Stop streaming on run_completed or run_failed
            try:
                parsed = json.loads(message["data"]) if message else {}
                if parsed.get("event") in ("run_completed", "run_failed"):
                    yield f"data: {json.dumps({'event': 'stream_end'})}\n\n"
                    break
            except Exception:
                pass

    finally:
        await pubsub.unsubscribe(channel_name)
        await pubsub.aclose()
        logger.info("sse_unsubscribed", run_id=run_id)


@router.get("/{run_id}")
async def stream_run_events(
    run_id: str,
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
) -> StreamingResponse:
    """
    SSE endpoint — streams real-time agent progress events to the browser.

    Events emitted:
    - ``agent_started``    → agent name + timestamp
    - ``agent_completed``  → agent name + result_summary + timestamp
    - ``hitl_required``    → hitl_id + payload_preview + timestamp
    - ``run_completed``    → summary + timestamp
    - ``run_failed``       → error + timestamp
    - ``: heartbeat``      → keep-alive every 15 s
    """
    mm = request.app.state.memory_manager
    redis_client: Redis = mm._redis.client

    return StreamingResponse(
        _event_generator(run_id, redis_client, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
