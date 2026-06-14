"""GitHub client — fully async repository operations via the GitHub REST API."""

from __future__ import annotations

import base64
from typing import Any

import httpx
from loguru import logger as _logger

logger = _logger.bind(module=__name__)

# ── Custom exceptions ──────────────────────────────────────────────────────


class GitHubAPIError(Exception):
    """Raised on non-404 HTTP errors from the GitHub API."""

    def __init__(
        self,
        message: str,
        endpoint: str,
        status_code: int,
    ) -> None:
        self.endpoint = endpoint
        self.status_code = status_code
        super().__init__(message)

    def __repr__(self) -> str:
        return (
            f"GitHubAPIError(endpoint={self.endpoint!r}, "
            f"status_code={self.status_code})"
        )


class GitHubNotFoundError(GitHubAPIError):
    """Raised when the GitHub API returns 404."""

    def __init__(self, endpoint: str) -> None:
        super().__init__(
            message=f"GitHub resource not found: {endpoint}",
            endpoint=endpoint,
            status_code=404,
        )


# ── Filter patterns ───────────────────────────────────────────────────────

_IGNORED_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        ".git",
        "dist",
        "build",
        ".next",
        "__pycache__",
        ".cache",
        ".turbo",
        "coverage",
        ".nyc_output",
    }
)

_IGNORED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".lock",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".svg",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".mp4",
        ".webm",
        ".mp3",
        ".zip",
        ".tar",
        ".gz",
    }
)


def _should_include(path: str) -> bool:
    """Return True if a file path should be included in the tree."""
    parts = path.split("/")
    # Skip files inside ignored directories
    for part in parts[:-1]:
        if part in _IGNORED_DIRS:
            return False
    # Skip lock files and binary extensions
    filename = parts[-1]
    if filename.endswith(".lock") or filename == "package-lock.json":
        return False
    for ext in _IGNORED_EXTENSIONS:
        if filename.endswith(ext):
            return False
    return True


# ── Client ─────────────────────────────────────────────────────────────────

_MAX_FILE_SIZE = 100 * 1024  # 100 KB


class GitHubClient:
    """Fully async GitHub REST API client using httpx.

    Parameters:
        token: GitHub personal access token or fine-grained token.
        repo: Repository in ``owner/name`` format.
    """

    def __init__(self, token: str, repo: str) -> None:
        self._repo = repo
        self._base_url = "https://api.github.com"
        self._headers: dict[str, str] = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=30.0,
        )
        self._default_branch: str | None = None
        logger.info("GitHubClient initialised for repo {}", self._repo)

    # ── HTTP helpers ───────────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Execute an HTTP request and return the parsed JSON response."""
        logger.debug("{} {}", method, endpoint)
        response = await self._client.request(
            method,
            endpoint,
            json=json,
            params=params,
        )

        if response.status_code == 404:
            raise GitHubNotFoundError(endpoint)

        if response.status_code >= 400:
            body = response.text[:500]
            logger.error(
                "GitHub API error {} on {}: {}",
                response.status_code,
                endpoint,
                body,
            )
            raise GitHubAPIError(
                message=f"GitHub API {response.status_code}: {body}",
                endpoint=endpoint,
                status_code=response.status_code,
            )

        if response.status_code == 204:
            return {}

        try:
            return response.json()
        except Exception as exc:
            raise GitHubAPIError(
                message=f"Failed to parse GitHub JSON: {exc}",
                endpoint=endpoint,
                status_code=response.status_code,
            ) from exc

    async def _get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        return await self._request("GET", endpoint, params=params)

    async def _post(
        self,
        endpoint: str,
        json: dict[str, Any],
    ) -> Any:
        return await self._request("POST", endpoint, json=json)

    async def _put(
        self,
        endpoint: str,
        json: dict[str, Any],
    ) -> Any:
        return await self._request("PUT", endpoint, json=json)

    # ── Branch resolution ──────────────────────────────────────────────────

    async def _resolve_branch(self, branch: str | None) -> str:
        """Return the branch to use, falling back to the repo default."""
        if branch is not None:
            return branch
        if self._default_branch is None:
            self._default_branch = await self.get_default_branch()
        return self._default_branch

    # ── Public methods ─────────────────────────────────────────────────────

    async def get_default_branch(self) -> str:
        """Return the repository's default branch name."""
        endpoint = f"/repos/{self._repo}"
        data = await self._get(endpoint)
        branch = data["default_branch"]
        self._default_branch = branch
        logger.info("Default branch for {}: {}", self._repo, branch)
        return branch

    async def get_file_tree(
        self,
        branch: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return the full file tree of the repository.

        Filters out binary files, lock files, and common build directories
        (node_modules, dist, .next, __pycache__, etc.).

        Returns a list of dicts with keys: path, type, sha, size.
        """
        branch = await self._resolve_branch(branch)
        endpoint = f"/repos/{self._repo}/git/trees/{branch}"
        data = await self._get(endpoint, params={"recursive": "1"})

        tree: list[dict[str, Any]] = []
        for item in data.get("tree", []):
            if item.get("type") != "blob":
                continue
            path: str = item.get("path", "")
            if not _should_include(path):
                continue
            tree.append(
                {
                    "path": path,
                    "type": "blob",
                    "sha": item.get("sha", ""),
                    "size": item.get("size", 0),
                }
            )

        logger.info(
            "File tree for {}@{}: {} files (filtered from {} entries)",
            self._repo,
            branch,
            len(tree),
            len(data.get("tree", [])),
        )
        return tree

    async def get_file_content(
        self,
        path: str,
        branch: str | None = None,
    ) -> dict[str, Any]:
        """Return the content of a single file.

        Files larger than 100 KB return ``content=None`` and
        ``too_large=True`` to avoid memory issues.
        """
        branch = await self._resolve_branch(branch)
        endpoint = f"/repos/{self._repo}/contents/{path}"
        data = await self._get(endpoint, params={"ref": branch})

        file_size: int = data.get("size", 0)
        sha: str = data.get("sha", "")

        if file_size > _MAX_FILE_SIZE:
            logger.warning(
                "File too large to fetch inline: {} ({} bytes)",
                path,
                file_size,
            )
            return {
                "path": path,
                "content": None,
                "sha": sha,
                "size": file_size,
                "too_large": True,
            }

        raw_content: str = data.get("content", "")
        try:
            decoded = base64.b64decode(raw_content).decode("utf-8")
        except (UnicodeDecodeError, Exception) as exc:
            logger.warning("Cannot decode {} as UTF-8: {}", path, exc)
            decoded = base64.b64decode(raw_content).decode("latin-1")

        logger.info("Fetched content of {} @ {} ({} bytes)", path, branch, file_size)
        return {
            "path": path,
            "content": decoded,
            "sha": sha,
            "size": file_size,
            "encoding": "utf-8",
        }

    async def get_recent_commits(
        self,
        branch: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return recent commits with files-changed metadata.

        For each commit, an additional request fetches the list of changed
        files so callers can correlate file changes to commits.
        """
        branch = await self._resolve_branch(branch)
        endpoint = f"/repos/{self._repo}/commits"
        commits_data = await self._get(
            endpoint,
            params={"sha": branch, "per_page": str(limit)},
        )

        commits: list[dict[str, Any]] = []
        for c in commits_data:
            sha: str = c.get("sha", "")
            commit_info = c.get("commit", {})
            author_info = commit_info.get("author", {})

            # Fetch detailed commit to get files changed
            files_changed: list[str] = []
            try:
                detail = await self._get(f"/repos/{self._repo}/commits/{sha}")
                files_changed = [
                    f.get("filename", "")
                    for f in detail.get("files", [])
                ]
            except (GitHubAPIError, GitHubNotFoundError):
                logger.warning("Could not fetch commit detail for {}", sha[:8])

            commits.append(
                {
                    "sha": sha,
                    "message": commit_info.get("message", ""),
                    "author": author_info.get("name", "unknown"),
                    "date": author_info.get("date", ""),
                    "files_changed": files_changed,
                }
            )

        logger.info(
            "Fetched {} recent commits for {}@{}",
            len(commits),
            self._repo,
            branch,
        )
        return commits

    async def create_branch(
        self,
        branch_name: str,
        from_branch: str | None = None,
    ) -> str:
        """Create a new branch from the HEAD of *from_branch*.

        Returns the new branch name.
        """
        from_branch = await self._resolve_branch(from_branch)

        # Get the SHA of the source branch HEAD
        ref_data = await self._get(
            f"/repos/{self._repo}/git/ref/heads/{from_branch}"
        )
        source_sha: str = ref_data.get("object", {}).get("sha", "")

        if not source_sha:
            raise GitHubAPIError(
                message=f"Could not resolve HEAD sha for branch {from_branch}",
                endpoint=f"/repos/{self._repo}/git/ref/heads/{from_branch}",
                status_code=0,
            )

        # Create the new ref
        await self._post(
            f"/repos/{self._repo}/git/refs",
            json={
                "ref": f"refs/heads/{branch_name}",
                "sha": source_sha,
            },
        )

        logger.info(
            "Created branch {} from {}@{} (sha={})",
            branch_name,
            from_branch,
            self._repo,
            source_sha[:8],
        )
        return branch_name

    async def create_or_update_file(
        self,
        path: str,
        content: str,
        message: str,
        branch: str,
        sha: str | None = None,
    ) -> dict[str, str]:
        """Create or update a file in the repository.

        If *sha* is provided the file is updated (overwritten); otherwise a
        new file is created.  Content is base64-encoded automatically.

        Returns ``{commit_sha, content_sha}``.
        """
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")

        payload: dict[str, Any] = {
            "message": message,
            "content": encoded,
            "branch": branch,
        }
        if sha is not None:
            payload["sha"] = sha

        endpoint = f"/repos/{self._repo}/contents/{path}"
        data = await self._put(endpoint, json=payload)

        commit_sha: str = data.get("commit", {}).get("sha", "")
        content_sha: str = data.get("content", {}).get("sha", "")

        action = "Updated" if sha else "Created"
        logger.info(
            "{} file {} on branch {} (commit={})",
            action,
            path,
            branch,
            commit_sha[:8],
        )
        return {"commit_sha": commit_sha, "content_sha": content_sha}

    async def create_pull_request(
        self,
        title: str,
        body: str,
        head: str,
        base: str | None = None,
    ) -> dict[str, Any]:
        """Create a pull request.

        Returns ``{number, url, html_url, state}``.
        """
        base = await self._resolve_branch(base)

        data = await self._post(
            f"/repos/{self._repo}/pulls",
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
            },
        )

        result = {
            "number": data.get("number"),
            "url": data.get("url", ""),
            "html_url": data.get("html_url", ""),
            "state": data.get("state", ""),
        }

        logger.info(
            "Created PR #{} ({} → {}): {}",
            result["number"],
            head,
            base,
            result["html_url"],
        )
        return result

    async def get_pull_request(self, pr_number: int) -> dict[str, Any]:
        """Fetch pull request details.

        Returns ``{number, state, merged, merge_commit_sha}``.
        """
        endpoint = f"/repos/{self._repo}/pulls/{pr_number}"
        data = await self._get(endpoint)

        result = {
            "number": data.get("number"),
            "state": data.get("state", ""),
            "merged": data.get("merged", False),
            "merge_commit_sha": data.get("merge_commit_sha", ""),
        }

        logger.info(
            "PR #{}: state={}, merged={}",
            pr_number,
            result["state"],
            result["merged"],
        )
        return result

    async def get_repo_languages(self) -> dict[str, int]:
        """Return the language breakdown of the repository.

        Returns a dict mapping language name → bytes of code.
        """
        endpoint = f"/repos/{self._repo}/languages"
        data = await self._get(endpoint)
        logger.info(
            "Repository languages for {}: {}",
            self._repo,
            ", ".join(f"{k}={v}" for k, v in data.items()),
        )
        return data

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()
        logger.info("GitHubClient closed for {}", self._repo)

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
