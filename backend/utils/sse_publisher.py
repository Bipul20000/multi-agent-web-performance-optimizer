"""SSE publisher — Redis pub/sub + asyncio queues for real-time event streaming."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import redis.asyncio as aioredis
from loguru import logger as _logger

logger = _logger.bind(module=__name__)

# ── Constants ──────────────────────────────────────────────────────────────

_KEEPALIVE_INTERVAL: float = 15.0  # seconds between keepalive pings
_STREAM_TIMEOUT: float = 600.0  # 10 minutes max stream lifetime
_CLEANUP_DELAY: float = 60.0  # seconds before cleaning up a finished queue
_TERMINAL_EVENTS: frozenset[str] = frozenset({"run_complete", "run_error"})


# ── Client ─────────────────────────────────────────────────────────────────


class SSEPublisher:
    """Publishes and streams Server-Sent Events for AWPIS pipeline runs.

    Events are published to both an in-memory ``asyncio.Queue`` (for
    same-process SSE streaming) and a Redis pub/sub channel (for
    multi-process / multi-worker deployments).

    Redis channel pattern: ``awpis:run:{run_id}``

    Parameters:
        redis_url: Redis connection string (e.g. ``redis://localhost:6379``).
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._redis: aioredis.Redis = aioredis.from_url(
            redis_url,
            decode_responses=True,
        )
        # In-memory queues for same-process streaming
        self._queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        # Per-run step counters (local; authoritative counter lives in Redis)
        self._step_counters: dict[str, int] = {}
        logger.info("SSEPublisher initialised (redis={})", redis_url)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _channel(self, run_id: str) -> str:
        """Return the Redis pub/sub channel name for a run."""
        return f"awpis:run:{run_id}"

    def _get_queue(self, run_id: str) -> asyncio.Queue[dict[str, Any]]:
        """Get or create the in-memory event queue for a run."""
        if run_id not in self._queues:
            self._queues[run_id] = asyncio.Queue()
            logger.debug("Created local SSE queue for run_id={}", run_id)
        return self._queues[run_id]

    def _build_event(
        self,
        run_id: str,
        event_type: str,
        agent_name: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Build a canonical event dict."""
        step_index = self._step_counters.get(run_id, 0)
        self._step_counters[run_id] = step_index + 1

        return {
            "run_id": run_id,
            "event_type": event_type,
            "agent_name": agent_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
            "step_index": step_index,
        }

    # ── Core publish ───────────────────────────────────────────────────────

    async def publish(
        self,
        run_id: str,
        event_type: str,
        agent_name: str,
        data: dict[str, Any],
    ) -> None:
        """Publish an event to both the local queue and Redis.

        The event is built with an auto-incrementing ``step_index`` and an
        ISO timestamp.  The Redis step counter is atomically incremented.
        """
        event = self._build_event(run_id, event_type, agent_name, data)
        event_json = json.dumps(event)

        # Local queue
        queue = self._get_queue(run_id)
        await queue.put(event)

        # Redis pub/sub + counter
        try:
            channel = self._channel(run_id)
            await self._redis.publish(channel, event_json)
            await self._redis.incr(f"awpis:steps:{run_id}")
        except Exception as exc:
            logger.warning(
                "Redis publish failed for run_id={}: {} (local queue still works)",
                run_id,
                exc,
            )

        logger.debug(
            "Published event: run_id={} type={} agent={} step={}",
            run_id,
            event_type,
            agent_name,
            event["step_index"],
        )

    # ── SSE subscribe (generator) ──────────────────────────────────────────

    async def subscribe(
        self,
        run_id: str,
    ) -> AsyncGenerator[str, None]:
        """Yield SSE-formatted strings for a given run.

        Yields ``data: {json}\\n\\n`` lines.  Sends a keepalive ping every
        15 seconds if no real event arrives.  Terminates when a
        ``run_complete`` or ``run_error`` event is received, or after
        10 minutes.
        """
        queue = self._get_queue(run_id)
        start = asyncio.get_event_loop().time()

        logger.info("SSE subscribe started for run_id={}", run_id)

        try:
            while True:
                elapsed = asyncio.get_event_loop().time() - start
                if elapsed > _STREAM_TIMEOUT:
                    logger.warning(
                        "SSE stream timeout after {:.0f}s for run_id={}",
                        elapsed,
                        run_id,
                    )
                    timeout_event = {
                        "run_id": run_id,
                        "event_type": "stream_timeout",
                        "agent_name": "",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": {"message": "Stream timeout after 10 minutes"},
                        "step_index": -1,
                    }
                    yield f"data: {json.dumps(timeout_event)}\n\n"
                    break

                try:
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=_KEEPALIVE_INTERVAL,
                    )
                except asyncio.TimeoutError:
                    # Send keepalive ping
                    ping = {
                        "event_type": "ping",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    yield f"data: {json.dumps(ping)}\n\n"
                    continue

                event_json = json.dumps(event)
                yield f"data: {event_json}\n\n"

                # Check for terminal events
                event_type = event.get("event_type", "")
                if event_type in _TERMINAL_EVENTS:
                    logger.info(
                        "SSE stream ending for run_id={} (event_type={})",
                        run_id,
                        event_type,
                    )
                    break
        finally:
            logger.info("SSE subscribe ended for run_id={}", run_id)

    # ── Convenience publishers ─────────────────────────────────────────────

    async def publish_agent_start(
        self,
        run_id: str,
        agent_name: str,
        input_summary: str,
    ) -> None:
        """Publish an ``agent_start`` event."""
        await self.publish(
            run_id=run_id,
            event_type="agent_start",
            agent_name=agent_name,
            data={"input_summary": input_summary},
        )

    async def publish_agent_complete(
        self,
        run_id: str,
        agent_name: str,
        output_summary: str,
        duration_ms: int,
    ) -> None:
        """Publish an ``agent_complete`` event."""
        await self.publish(
            run_id=run_id,
            event_type="agent_complete",
            agent_name=agent_name,
            data={
                "output_summary": output_summary,
                "duration_ms": duration_ms,
            },
        )

    async def publish_agent_error(
        self,
        run_id: str,
        agent_name: str,
        error: str,
        duration_ms: int = 0,
    ) -> None:
        """Publish an ``agent_error`` event."""
        await self.publish(
            run_id=run_id,
            event_type="agent_error",
            agent_name=agent_name,
            data={
                "error": error,
                "duration_ms": duration_ms,
            },
        )

    async def publish_gate_result(
        self,
        run_id: str,
        gate_name: str,
        result: str,
        details: str,
    ) -> None:
        """Publish a ``gate_result`` event."""
        await self.publish(
            run_id=run_id,
            event_type="gate_result",
            agent_name=gate_name,
            data={
                "result": result,
                "details": details,
            },
        )

    async def publish_metric_update(
        self,
        run_id: str,
        agent_name: str,
        metrics: dict[str, Any],
    ) -> None:
        """Publish a ``metric_update`` event."""
        await self.publish(
            run_id=run_id,
            event_type="metric_update",
            agent_name=agent_name,
            data={"metrics": metrics},
        )

    async def publish_run_complete(
        self,
        run_id: str,
        summary: dict[str, Any],
    ) -> None:
        """Publish a ``run_complete`` event and schedule queue cleanup."""
        await self.publish(
            run_id=run_id,
            event_type="run_complete",
            agent_name="pipeline",
            data=summary,
        )

        # Schedule cleanup after a delay to give SSE subscribers time to read
        asyncio.get_event_loop().call_later(
            _CLEANUP_DELAY,
            lambda: self._cleanup_run(run_id),
        )

    async def publish_run_error(
        self,
        run_id: str,
        error: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Publish a ``run_error`` event and schedule queue cleanup."""
        await self.publish(
            run_id=run_id,
            event_type="run_error",
            agent_name="pipeline",
            data={
                "error": error,
                "details": details or {},
            },
        )

        asyncio.get_event_loop().call_later(
            _CLEANUP_DELAY,
            lambda: self._cleanup_run(run_id),
        )

    # ── Internal cleanup ───────────────────────────────────────────────────

    def _cleanup_run(self, run_id: str) -> None:
        """Remove the local queue and step counter for a finished run."""
        self._queues.pop(run_id, None)
        self._step_counters.pop(run_id, None)
        logger.debug("Cleaned up SSE resources for run_id={}", run_id)

    # ── Health ─────────────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Verify Redis connectivity."""
        try:
            result = await self._redis.ping()
            logger.info("Redis ping: {}", "OK" if result else "FAILED")
            return bool(result)
        except Exception as exc:
            logger.error("Redis ping failed: {}", exc)
            return False

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the Redis connection and clean up all queues."""
        self._queues.clear()
        self._step_counters.clear()
        try:
            await self._redis.aclose()
        except Exception as exc:
            logger.warning("Error closing Redis connection: {}", exc)
        logger.info("SSEPublisher closed")

    async def __aenter__(self) -> SSEPublisher:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
