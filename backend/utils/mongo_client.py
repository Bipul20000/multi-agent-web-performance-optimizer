"""MongoDB client — async operations via Motor for runs, fix memory, and baselines."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger as _logger
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

logger = _logger.bind(module=__name__)

# ── Custom exceptions ──────────────────────────────────────────────────────


class MongoDBError(Exception):
    """Raised when a MongoDB operation fails."""

    def __init__(self, message: str, operation: str = "") -> None:
        self.operation = operation
        super().__init__(message)


# ── Client ─────────────────────────────────────────────────────────────────


class MongoClient:
    """Async MongoDB client wrapping Motor for AWPIS-specific collections.

    Collections:
        - **runs**: Pipeline run records with metrics, fixes, and outcomes.
        - **fix_memory**: Historical fix attempts and their results.
        - **baselines**: Per-URL baseline performance scores.

    Parameters:
        uri: MongoDB connection string.
        db_name: Database name (default ``awpis``).
    """

    def __init__(self, uri: str, db_name: str = "awpis") -> None:
        self._uri = uri
        self._db_name = db_name
        try:
            self._motor: AsyncIOMotorClient = AsyncIOMotorClient(uri)
            self._db: AsyncIOMotorDatabase = self._motor[db_name]
        except Exception as exc:
            raise MongoDBError(
                f"Failed to create Motor client: {exc}",
                operation="init",
            ) from exc
        logger.info("MongoClient initialised (db={})", db_name)

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def runs(self):
        """Return the ``runs`` collection handle."""
        return self._db.runs

    @property
    def fix_memory(self):
        """Return the ``fix_memory`` collection handle."""
        return self._db.fix_memory

    @property
    def baselines(self):
        """Return the ``baselines`` collection handle."""
        return self._db.baselines

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _serialise_doc(doc: dict[str, Any]) -> dict[str, Any]:
        """Convert MongoDB ``_id`` (ObjectId) to a string for JSON safety."""
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc

    # ── Health ─────────────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Verify connectivity to the MongoDB server.

        Returns ``True`` if the server responds, ``False`` otherwise.
        """
        try:
            result = await self._motor.admin.command("ping")
            ok = result.get("ok") == 1.0
            logger.info("MongoDB ping: {}", "OK" if ok else "FAILED")
            return ok
        except Exception as exc:
            logger.error("MongoDB ping failed: {}", exc)
            return False

    # ── Runs ───────────────────────────────────────────────────────────────

    async def save_run(self, run_data: dict[str, Any]) -> str:
        """Insert a new run document.

        *run_data* must contain a ``run_id`` field.  A ``start_time`` is
        added automatically if not already present.

        Returns the inserted document ID as a string.
        """
        if "run_id" not in run_data:
            raise MongoDBError(
                "run_data must contain a 'run_id' field",
                operation="save_run",
            )

        run_data.setdefault(
            "start_time",
            datetime.now(timezone.utc).isoformat(),
        )

        try:
            result = await self.runs.insert_one(run_data)
            doc_id = str(result.inserted_id)
            logger.info(
                "Saved run {} (doc_id={})",
                run_data["run_id"],
                doc_id,
            )
            return doc_id
        except Exception as exc:
            raise MongoDBError(
                f"Failed to save run: {exc}",
                operation="save_run",
            ) from exc

    async def update_run(self, run_id: str, update_data: dict[str, Any]) -> bool:
        """Update an existing run document via ``$set``.

        Returns ``True`` if a document was matched (and updated).
        """
        try:
            result = await self.runs.update_one(
                {"run_id": run_id},
                {"$set": update_data},
            )
            matched = result.matched_count > 0
            logger.info(
                "Updated run {} — matched={}",
                run_id,
                matched,
            )
            return matched
        except Exception as exc:
            raise MongoDBError(
                f"Failed to update run {run_id}: {exc}",
                operation="update_run",
            ) from exc

    async def get_recent_runs(
        self,
        client_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return the most recent run summaries.

        Optionally filtered by *client_id*.  Sorted by ``start_time``
        descending.
        """
        query: dict[str, Any] = {}
        if client_id is not None:
            query["client_id"] = client_id

        try:
            cursor = (
                self.runs.find(query)
                .sort("start_time", -1)
                .limit(limit)
            )
            runs: list[dict[str, Any]] = []
            async for doc in cursor:
                runs.append(self._serialise_doc(doc))
            logger.info("Fetched {} recent runs", len(runs))
            return runs
        except Exception as exc:
            raise MongoDBError(
                f"Failed to fetch recent runs: {exc}",
                operation="get_recent_runs",
            ) from exc

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Fetch a single run by ``run_id``.

        Returns the document dict or ``None`` if not found.
        """
        try:
            doc = await self.runs.find_one({"run_id": run_id})
            if doc is None:
                logger.info("Run {} not found", run_id)
                return None
            logger.info("Fetched run {}", run_id)
            return self._serialise_doc(doc)
        except Exception as exc:
            raise MongoDBError(
                f"Failed to fetch run {run_id}: {exc}",
                operation="get_run",
            ) from exc

    # ── Fix memory ─────────────────────────────────────────────────────────

    async def save_fix_memory(self, memory_entry: dict[str, Any]) -> str:
        """Persist a fix-memory entry.

        Required keys: ``fix_type``, ``stack``, ``metric_targeted``,
        ``before``, ``after``, ``success``, ``page_type``, ``timestamp``.
        """
        required_keys = {
            "fix_type",
            "stack",
            "metric_targeted",
            "before",
            "after",
            "success",
            "page_type",
            "timestamp",
        }
        missing = required_keys - set(memory_entry.keys())
        if missing:
            raise MongoDBError(
                f"fix_memory entry missing required keys: {missing}",
                operation="save_fix_memory",
            )

        try:
            result = await self.fix_memory.insert_one(memory_entry)
            doc_id = str(result.inserted_id)
            logger.info(
                "Saved fix_memory entry (type={}, success={}, id={})",
                memory_entry["fix_type"],
                memory_entry["success"],
                doc_id,
            )
            return doc_id
        except Exception as exc:
            raise MongoDBError(
                f"Failed to save fix_memory: {exc}",
                operation="save_fix_memory",
            ) from exc

    async def get_fix_memory(
        self,
        stack: str | None = None,
        metric: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Query fix memory with optional filters.

        Results are sorted so successes appear first, then failures,
        both ordered by ``timestamp`` descending.
        """
        query: dict[str, Any] = {}
        if stack is not None:
            query["stack"] = stack
        if metric is not None:
            query["metric_targeted"] = metric

        try:
            # Fetch successes first, then failures, both sorted by timestamp
            successes_cursor = (
                self.fix_memory.find({**query, "success": True})
                .sort("timestamp", -1)
                .limit(limit)
            )
            successes: list[dict[str, Any]] = []
            async for doc in successes_cursor:
                successes.append(self._serialise_doc(doc))

            remaining = limit - len(successes)
            failures: list[dict[str, Any]] = []
            if remaining > 0:
                failures_cursor = (
                    self.fix_memory.find({**query, "success": False})
                    .sort("timestamp", -1)
                    .limit(remaining)
                )
                async for doc in failures_cursor:
                    failures.append(self._serialise_doc(doc))

            result = successes + failures
            logger.info(
                "Fetched {} fix_memory entries ({} successes, {} failures)",
                len(result),
                len(successes),
                len(failures),
            )
            return result
        except Exception as exc:
            raise MongoDBError(
                f"Failed to query fix_memory: {exc}",
                operation="get_fix_memory",
            ) from exc

    # ── Baselines ──────────────────────────────────────────────────────────

    async def save_baseline(self, url: str, scores: dict[str, Any]) -> None:
        """Upsert a baseline for *url*.

        Only updates the stored baseline if the new performance score is
        higher than the existing one (i.e. we keep the best-known baseline).
        """
        try:
            existing = await self.baselines.find_one({"url": url})

            new_perf = scores.get("performance", 0.0)

            if existing is not None:
                old_perf = existing.get("scores", {}).get("performance", 0.0)
                if new_perf <= old_perf:
                    logger.info(
                        "Baseline for {} not updated — existing ({}) >= new ({})",
                        url,
                        old_perf,
                        new_perf,
                    )
                    return

            await self.baselines.update_one(
                {"url": url},
                {
                    "$set": {
                        "url": url,
                        "scores": scores,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                },
                upsert=True,
            )
            logger.info(
                "Baseline saved for {} (performance={})",
                url,
                new_perf,
            )
        except Exception as exc:
            raise MongoDBError(
                f"Failed to save baseline for {url}: {exc}",
                operation="save_baseline",
            ) from exc

    async def get_baseline(self, url: str) -> dict[str, Any] | None:
        """Fetch the baseline for *url*.

        Returns the document dict or ``None`` if no baseline exists.
        """
        try:
            doc = await self.baselines.find_one({"url": url})
            if doc is None:
                logger.info("No baseline found for {}", url)
                return None
            logger.info("Fetched baseline for {}", url)
            return self._serialise_doc(doc)
        except Exception as exc:
            raise MongoDBError(
                f"Failed to fetch baseline for {url}: {exc}",
                operation="get_baseline",
            ) from exc

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the Motor client connection."""
        self._motor.close()
        logger.info("MongoClient closed (db={})", self._db_name)

    async def __aenter__(self) -> MongoClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
