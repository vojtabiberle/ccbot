"""Zellij backend for the multiplexer abstraction.

Implements MultiplexerBackend using Zellij CLI via asyncio.create_subprocess_exec.
Zellij actions are focus-dependent (operate on the focused tab/pane), so all
operations that need tab targeting are serialized with an asyncio.Lock.

Limitations vs tmux:
  - No ANSI color capture (plain text only — /screenshot lower quality)
  - No headless session creation (session must pre-exist)
  - Tab close/kill is focus-dependent (navigate first, then close)

Key class: ZellijBackend(MultiplexerBackend).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from pathlib import Path

from ..config import config
from .base import MultiplexerBackend, MuxWindow

logger = logging.getLogger(__name__)

# ANSI fallback warning (logged once)
_ansi_warned = False


class ZellijBackend(MultiplexerBackend):
    """Manages Zellij tabs for Claude Code sessions."""

    def __init__(self, session_name: str, main_window_name: str) -> None:
        super().__init__(session_name, main_window_name)
        # Serialize all focus-dependent operations
        self._lock = asyncio.Lock()

    async def _run(
        self, *args: str, check: bool = True,
    ) -> tuple[int, str, str]:
        """Run a subprocess and return (returncode, stdout, stderr)."""
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        rc = proc.returncode or 0
        if check and rc != 0:
            logger.debug("Command %s failed (rc=%d): %s", args, rc, stderr.strip())
        return rc, stdout, stderr

    async def _zellij_action(self, *action_args: str) -> tuple[int, str, str]:
        """Run `zellij --session <name> action <action_args>`."""
        return await self._run(
            "zellij", "--session", self.session_name, "action", *action_args,
        )

    def get_or_create_session(self) -> None:
        """Verify the Zellij session exists (cannot create headlessly)."""
        import subprocess

        result = subprocess.run(
            ["zellij", "list-sessions", "--short", "--no-formatting"],
            capture_output=True, text=True,
        )
        sessions = [s.strip() for s in result.stdout.strip().splitlines() if s.strip()]
        if self.session_name in sessions:
            return

        raise RuntimeError(
            f"Zellij session '{self.session_name}' not found. "
            f"Please create it first: zellij -s {self.session_name}"
        )

    async def list_windows(self) -> list[MuxWindow]:
        """List all tabs in the session via query-tab-names + dump-layout."""
        # Get tab names
        rc, stdout, _ = await self._zellij_action("query-tab-names")
        if rc != 0:
            return []

        tab_names = [n.strip() for n in stdout.strip().splitlines() if n.strip()]

        # Parse cwds from dump-layout KDL
        cwds = await self._parse_tab_cwds()

        windows: list[MuxWindow] = []
        for name in tab_names:
            if name == self.main_window_name:
                continue
            cwd = cwds.get(name, "")
            windows.append(MuxWindow(
                window_id=name,  # Zellij uses tab name as ID
                window_name=name,
                cwd=cwd,
            ))
        return windows

    async def _parse_tab_cwds(self) -> dict[str, str]:
        """Parse tab cwds from dump-layout KDL output.

        Looks for patterns like: tab name="xxx" { pane cwd="/path" }
        """
        rc, stdout, _ = await self._zellij_action("dump-layout")
        if rc != 0:
            return {}

        result: dict[str, str] = {}
        # Match tab blocks with name and extract first cwd from pane
        # KDL format: tab name="tabname" { ... pane cwd="/path" ... }
        tab_pattern = re.compile(
            r'tab\s[^{]*?name="([^"]+)"[^{]*\{([^}]*)\}',
            re.DOTALL,
        )
        cwd_pattern = re.compile(r'cwd="([^"]+)"')

        for match in tab_pattern.finditer(stdout):
            tab_name = match.group(1)
            tab_body = match.group(2)
            cwd_match = cwd_pattern.search(tab_body)
            if cwd_match:
                result[tab_name] = cwd_match.group(1)

        return result

    async def capture_pane(self, window_id: str, with_ansi: bool = False) -> str | None:
        """Capture pane content via dump-screen."""
        global _ansi_warned
        if with_ansi and not _ansi_warned:
            logger.warning(
                "Zellij does not support ANSI color capture; "
                "falling back to plain text"
            )
            _ansi_warned = True

        async with self._lock:
            # Navigate to the tab
            rc, _, _ = await self._zellij_action("go-to-tab-name", window_id)
            if rc != 0:
                return None

            # Dump screen to temp file
            tmp_file = os.path.join(tempfile.gettempdir(), f"ccbot_zellij_{os.getpid()}.txt")
            try:
                rc, _, _ = await self._zellij_action("dump-screen", tmp_file)
                if rc != 0:
                    return None

                try:
                    return Path(tmp_file).read_text(encoding="utf-8", errors="replace")
                except OSError as e:
                    logger.error("Failed to read dump-screen output: %s", e)
                    return None
            finally:
                try:
                    os.unlink(tmp_file)
                except OSError:
                    pass

    async def send_keys(
        self, window_id: str, text: str, enter: bool = True, literal: bool = True,
    ) -> bool:
        """Send keys to a Zellij tab."""
        async with self._lock:
            # Navigate to the tab
            rc, _, _ = await self._zellij_action("go-to-tab-name", window_id)
            if rc != 0:
                logger.error("Failed to navigate to tab %s", window_id)
                return False

            if literal:
                # Send text literally
                if text:
                    rc, _, _ = await self._zellij_action("write-chars", text)
                    if rc != 0:
                        logger.error("Failed to write-chars to tab %s", window_id)
                        return False

                if enter:
                    # Small delay for TUI to process text before Enter
                    await asyncio.sleep(0.5)
                    rc, _, _ = await self._zellij_action("write", "13")
                    if rc != 0:
                        logger.error("Failed to send Enter to tab %s", window_id)
                        return False
            else:
                # Interpret special key names
                sent = await self._send_special_key(text)
                if not sent:
                    logger.error("Failed to send special key %r to tab %s", text, window_id)
                    return False

            return True

    async def _send_special_key(self, key: str) -> bool:
        """Send a special key by name or byte value."""
        # Map key names to Zellij write byte values or ANSI sequences
        key_lower = key.lower()

        if key_lower in ("escape", "\x1b"):
            rc, _, _ = await self._zellij_action("write", "27")
            return rc == 0
        elif key_lower == "enter":
            rc, _, _ = await self._zellij_action("write", "13")
            return rc == 0
        elif key_lower == "up":
            rc, _, _ = await self._zellij_action("write-chars", "\x1b[A")
            return rc == 0
        elif key_lower == "down":
            rc, _, _ = await self._zellij_action("write-chars", "\x1b[B")
            return rc == 0
        elif key_lower == "right":
            rc, _, _ = await self._zellij_action("write-chars", "\x1b[C")
            return rc == 0
        elif key_lower == "left":
            rc, _, _ = await self._zellij_action("write-chars", "\x1b[D")
            return rc == 0
        else:
            # Unknown key, try sending as chars
            rc, _, _ = await self._zellij_action("write-chars", key)
            return rc == 0

    async def kill_window(self, window_id: str) -> bool:
        """Kill a Zellij tab."""
        async with self._lock:
            rc, _, _ = await self._zellij_action("go-to-tab-name", window_id)
            if rc != 0:
                return False

            rc, _, _ = await self._zellij_action("close-tab")
            if rc == 0:
                logger.info("Killed tab %s", window_id)
                return True
            logger.error("Failed to close tab %s", window_id)
            return False

    async def create_window(
        self,
        work_dir: str,
        window_name: str | None = None,
        start_claude: bool = True,
    ) -> tuple[bool, str, str]:
        """Create a new Zellij tab and optionally start Claude Code."""
        # Validate directory first
        path = Path(work_dir).expanduser().resolve()
        if not path.exists():
            return False, f"Directory does not exist: {work_dir}", ""
        if not path.is_dir():
            return False, f"Not a directory: {work_dir}", ""

        # Create tab name, adding suffix if name already exists
        final_name = window_name if window_name else path.name
        base_name = final_name
        counter = 2
        while await self.find_window_by_name(final_name):
            final_name = f"{base_name}-{counter}"
            counter += 1

        try:
            # Create new tab with cwd
            rc, _, stderr = await self._run(
                "zellij", "--session", self.session_name,
                "action", "new-tab", "--name", final_name, "--cwd", str(path),
            )
            if rc != 0:
                return False, f"Failed to create tab: {stderr.strip()}", ""

            # Start Claude Code if requested
            if start_claude:
                await asyncio.sleep(0.3)  # Let the tab initialize
                rc, _, _ = await self._zellij_action("write-chars", config.claude_command)
                if rc == 0:
                    await asyncio.sleep(0.5)
                    await self._zellij_action("write", "13")  # Enter

            logger.info("Created tab '%s' at %s", final_name, path)
            return True, f"Created window '{final_name}' at {path}", final_name

        except Exception as e:
            logger.error("Failed to create tab: %s", e)
            return False, f"Failed to create tab: {e}", ""
