"""Async client for repo-manager CLI.

Wraps the ``repo-manager`` shell tool via :mod:`asyncio.subprocess`,
parses its TSV / JSON output, and exposes typed helper methods for
listing, adding, updating, and managing git worktrees.

Key class: RepoClient (singleton instantiated as ``repo_client``).
"""

import asyncio
import json
import logging
from dataclasses import dataclass

from .config import config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RepoInfo:
    """Single row returned by ``repo-manager list``."""

    name: str
    path: str
    branch: str
    dirty: bool


@dataclass(frozen=True)
class RepoStatus:
    """Detailed status returned by ``repo-manager status --json``."""

    name: str
    branch: str
    dirty: bool
    ahead: int
    behind: int
    last_commit: str
    last_commit_date: str
    url: str


@dataclass(frozen=True)
class WorktreeInfo:
    """Single worktree entry returned by ``repo-manager wt-list``."""

    path: str
    branch: str


class RepoClient:
    """Async wrapper around the ``repo-manager`` CLI."""

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    async def _run(
        self, *args: str, timeout: float = 30,
    ) -> str:
        """Execute ``repo-manager <args>`` and return stdout.

        Raises :class:`RuntimeError` on non-zero exit or timeout.
        """
        cmd = config.repo_manager_cmd
        full_args = [cmd, *args]
        logger.debug("repo-manager exec: %s", full_args)

        proc = await asyncio.create_subprocess_exec(
            *full_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise RuntimeError(
                f"repo-manager timed out after {timeout}s: {full_args}"
            )

        stdout = stdout_bytes.decode().strip()
        stderr = stderr_bytes.decode().strip()

        if proc.returncode != 0:
            raise RuntimeError(
                f"repo-manager exited {proc.returncode}: {stderr or stdout}"
            )

        return stdout

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    async def list_repos(self) -> list[RepoInfo]:
        """Return all registered repositories (``repo-manager list``)."""
        out = await self._run("list")
        if not out:
            return []

        repos: list[RepoInfo] = []
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            repos.append(RepoInfo(
                name=parts[0],
                path=parts[1],
                branch=parts[2],
                dirty=parts[3].lower() in ("true", "yes", "1", "dirty"),
            ))
        return repos

    async def add_repo(self, url: str, name: str | None = None) -> str:
        """Clone / register a repository. Returns the local path."""
        args = ["add", url]
        if name:
            args.append(name)
        return await self._run(*args, timeout=120)

    async def remove_repo(self, name: str) -> None:
        """Unregister a repository."""
        await self._run("remove", name)

    async def update_repos(
        self, name: str | None = None,
    ) -> list[tuple[str, str]]:
        """Fetch & pull repositories. Returns ``[(name, status_line)]``."""
        args = ["update"]
        if name:
            args.append(name)
        out = await self._run(*args, timeout=120)
        if not out:
            return []

        results: list[tuple[str, str]] = []
        for line in out.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                results.append((parts[0], parts[1]))
            else:
                results.append((line, ""))
        return results

    async def status(
        self, name: str | None = None,
    ) -> list[RepoStatus] | RepoStatus:
        """Return JSON status for one or all repos."""
        args = ["status"]
        if name:
            args.append(name)
        out = await self._run(*args)
        data = json.loads(out)

        def _parse(d: dict) -> RepoStatus:
            return RepoStatus(
                name=d.get("name", ""),
                branch=d.get("branch", ""),
                dirty=bool(d.get("dirty", False)),
                ahead=int(d.get("ahead", 0)),
                behind=int(d.get("behind", 0)),
                last_commit=d.get("last_commit", ""),
                last_commit_date=d.get("last_commit_date", ""),
                url=d.get("url", ""),
            )

        if isinstance(data, list):
            return [_parse(item) for item in data]
        return _parse(data)

    async def wt_list(self, name: str) -> list[WorktreeInfo]:
        """List worktrees for a repository."""
        out = await self._run("wt-list", name)
        if not out:
            return []

        worktrees: list[WorktreeInfo] = []
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                worktrees.append(WorktreeInfo(path=parts[0], branch=parts[1]))
        return worktrees

    async def wt_add(
        self, name: str, branch: str, source: str | None = None,
    ) -> str:
        """Create a worktree. Returns the worktree path."""
        args = ["wt-add", name, branch]
        if source:
            args.extend(["--from", source])
        return await self._run(*args, timeout=120)

    async def wt_rm(self, name: str, branch: str) -> None:
        """Remove a worktree."""
        await self._run("wt-rm", name, branch)

    async def scan(self) -> list[str]:
        """Scan for unregistered repos. Returns newly registered names."""
        out = await self._run("scan", timeout=120)
        if not out:
            return []
        return out.splitlines()


repo_client = RepoClient()
