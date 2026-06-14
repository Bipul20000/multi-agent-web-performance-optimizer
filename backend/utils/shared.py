"""Lazy-singleton accessors for cross-cutting infrastructure clients.

These avoid circular imports — agents import from here instead of
``backend.main``.  All imports are deferred into the factory functions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.utils.github_client import GitHubClient
    from backend.utils.mongo_client import MongoClient
    from backend.utils.sse_publisher import SSEPublisher

_publisher: SSEPublisher | None = None
_mongo: MongoClient | None = None
_github: GitHubClient | None = None


def get_publisher() -> SSEPublisher:
    """Return a process-wide :class:`SSEPublisher` singleton."""
    global _publisher
    if _publisher is None:
        from backend.config import get_settings
        from backend.utils.sse_publisher import SSEPublisher as _Cls

        _publisher = _Cls(get_settings().REDIS_URL)
    return _publisher


def get_mongo() -> MongoClient:
    """Return a process-wide :class:`MongoClient` singleton."""
    global _mongo
    if _mongo is None:
        from backend.config import get_settings
        from backend.utils.mongo_client import MongoClient as _Cls

        s = get_settings()
        _mongo = _Cls(uri=s.MONGODB_URI, db_name=s.DB_NAME)
    return _mongo


def get_github() -> GitHubClient:
    """Return a process-wide :class:`GitHubClient` singleton."""
    global _github
    if _github is None:
        from backend.config import get_settings
        from backend.utils.github_client import GitHubClient as _Cls

        s = get_settings()
        _github = _Cls(token=s.GITHUB_TOKEN, repo=s.GITHUB_REPO)
    return _github
