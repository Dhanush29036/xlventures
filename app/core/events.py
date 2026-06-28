"""
app/core/events.py — AgentEventPublisher.

Publishes structured JSON events to Redis channel ``run:{run_id}:events``.
SSE endpoint subscribes to this channel and forwards events to the browser.

All methods are async.  For sync Celery workers, use the ``publish_sync``
convenience wrapper that calls asyncio.run() safely.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)


def _channel(run_id: str) -> str:
    return f"run:{run_id}:events"


class AgentEventPublisher:
    """
    Publishes real-time agent progress events to Redis pub/sub.

    Parameters
    ----------
    redis_client:
        Connected ``redis.asyncio.Redis`` client.
    """

    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    async def publish(self, run_id: str, event_type: str, data: dict[str, Any]) -> None:
        payload = {
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data,
        }
        msg = json.dumps(payload, default=str)
        await self._redis.publish(_channel(run_id), msg)
        logger.debug("event_published", run_id=run_id, event_type=event_type)

    async def publish_agent_started(self, run_id: str, agent_name: str) -> None:
        await self.publish(run_id, "agent_started", {"agent": agent_name})

    async def publish_agent_completed(
        self, run_id: str, agent_name: str, summary: dict[str, Any]
    ) -> None:
        await self.publish(
            run_id, "agent_completed", {"agent": agent_name, "result_summary": summary}
        )

    async def publish_hitl_required(
        self, run_id: str, hitl_id: str, preview: dict[str, Any]
    ) -> None:
        await self.publish(
            run_id, "hitl_required", {"hitl_id": hitl_id, "payload_preview": preview}
        )

    async def publish_run_completed(self, run_id: str, summary: dict[str, Any]) -> None:
        await self.publish(run_id, "run_completed", {"summary": summary})

    async def publish_run_failed(self, run_id: str, error: str) -> None:
        await self.publish(run_id, "run_failed", {"error": error})


# ── Sync wrapper for Celery workers ──────────────────────────────────────────


def publish_event_sync(
    redis_url: str,
    run_id: str,
    event_type: str,
    data: dict[str, Any],
) -> None:
    """
    Fire-and-forget event publish for synchronous Celery task context.
    Creates a short-lived event loop to run the async publish.
    """

    async def _run() -> None:
        from redis.asyncio import from_url
        r = await from_url(redis_url, decode_responses=True)
        publisher = AgentEventPublisher(r)
        await publisher.publish(run_id, event_type, data)
        await r.aclose()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already inside an event loop (e.g., during tests)
            loop.create_task(_run())
        else:
            loop.run_until_complete(_run())
    except RuntimeError:
        asyncio.run(_run())
