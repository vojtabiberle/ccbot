"""Tmux backend for the multiplexer abstraction.

Wraps libtmux to provide async-friendly operations on a single tmux session:
  - list_windows / find_window_by_name: discover Claude Code windows.
  - capture_pane: read terminal content (plain or with ANSI colors).
  - send_keys: forward user input or control keys to a window.
  - create_window / kill_window: lifecycle management.

All blocking libtmux calls are wrapped in asyncio.to_thread().

Key class: TmuxBackend(MultiplexerBackend).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import libtmux

from ..config import config
from .base import MultiplexerBackend, MuxWindow

logger = logging.getLogger(__name__)


class TmuxBackend(MultiplexerBackend):
    """Manages tmux windows for Claude Code sessions."""

    def __init__(self, session_name: str, main_window_name: str) -> None:
        super().__init__(session_name, main_window_name)
        self._server: libtmux.Server | None = None

    @property
    def server(self) -> libtmux.Server:
        """Get or create tmux server connection."""
        if self._server is None:
            self._server = libtmux.Server()
        return self._server

    def get_session(self) -> libtmux.Session | None:
        """Get the tmux session if it exists."""
        try:
            return self.server.sessions.get(session_name=self.session_name)
        except Exception:
            return None

    def get_or_create_session(self) -> None:
        """Get existing session or create a new one."""
        session = self.get_session()
        if session:
            return

        # Create new session with main window named specifically
        session = self.server.new_session(
            session_name=self.session_name,
            start_directory=str(Path.home()),
        )
        # Rename the default window to the main window name
        if session.windows:
            session.windows[0].rename_window(self.main_window_name)

    async def list_windows(self) -> list[MuxWindow]:
        """List all windows in the session with their working directories."""

        def _sync_list_windows() -> list[MuxWindow]:
            windows = []
            session = self.get_session()

            if not session:
                return windows

            for window in session.windows:
                name = window.window_name or ""
                # Skip the main window (placeholder window)
                if name == self.main_window_name:
                    continue
                try:
                    # Get the active pane's current path
                    pane = window.active_pane
                    if pane:
                        cwd = pane.pane_current_path or ""
                    else:
                        cwd = ""

                    windows.append(
                        MuxWindow(
                            window_id=window.window_id or "",
                            window_name=window.window_name or "",
                            cwd=cwd,
                        )
                    )
                except Exception as e:
                    logger.debug(f"Error getting window info: {e}")

            return windows

        return await asyncio.to_thread(_sync_list_windows)

    async def capture_pane(self, window_id: str, with_ansi: bool = False) -> str | None:
        """Capture the visible text content of a window's active pane."""
        if with_ansi:
            # Use async subprocess to call tmux capture-pane -e for ANSI colors
            try:
                proc = await asyncio.create_subprocess_exec(
                    "tmux", "capture-pane", "-e", "-p", "-t", window_id,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode == 0:
                    return stdout.decode("utf-8")
                logger.error(f"Failed to capture pane {window_id}: {stderr.decode('utf-8')}")
                return None
            except Exception as e:
                logger.error(f"Unexpected error capturing pane {window_id}: {e}")
                return None

        # Original implementation for plain text - wrap in thread
        def _sync_capture() -> str | None:
            session = self.get_session()
            if not session:
                return None
            try:
                window = session.windows.get(window_id=window_id)
                if not window:
                    return None
                pane = window.active_pane
                if not pane:
                    return None
                lines = pane.capture_pane()
                return "\n".join(lines) if isinstance(lines, list) else str(lines)
            except Exception as e:
                logger.error(f"Failed to capture pane {window_id}: {e}")
                return None

        return await asyncio.to_thread(_sync_capture)

    async def send_keys(
        self, window_id: str, text: str, enter: bool = True, literal: bool = True,
    ) -> bool:
        """Send keys to a specific window."""
        if literal and enter:
            # Split into text + delay + Enter via libtmux.
            # Claude Code's TUI sometimes interprets a rapid-fire Enter
            # (arriving in the same input batch as the text) as a newline
            # rather than submit.  A 500ms gap lets the TUI process the
            # text before receiving Enter.
            def _send_text() -> bool:
                session = self.get_session()
                if not session:
                    logger.error("No tmux session found")
                    return False
                try:
                    window = session.windows.get(window_id=window_id)
                    if not window:
                        logger.error(f"Window {window_id} not found")
                        return False
                    pane = window.active_pane
                    if not pane:
                        logger.error(f"No active pane in window {window_id}")
                        return False
                    pane.send_keys(text, enter=False, literal=True)
                    return True
                except Exception as e:
                    logger.error(f"Failed to send keys to window {window_id}: {e}")
                    return False

            def _send_enter() -> bool:
                session = self.get_session()
                if not session:
                    return False
                try:
                    window = session.windows.get(window_id=window_id)
                    if not window:
                        return False
                    pane = window.active_pane
                    if not pane:
                        return False
                    pane.send_keys("", enter=True, literal=False)
                    return True
                except Exception as e:
                    logger.error(f"Failed to send Enter to window {window_id}: {e}")
                    return False

            if not await asyncio.to_thread(_send_text):
                return False
            await asyncio.sleep(0.5)
            return await asyncio.to_thread(_send_enter)

        # Other cases: special keys (literal=False) or no-enter
        def _sync_send_keys() -> bool:
            session = self.get_session()
            if not session:
                logger.error("No tmux session found")
                return False

            try:
                window = session.windows.get(window_id=window_id)
                if not window:
                    logger.error(f"Window {window_id} not found")
                    return False

                pane = window.active_pane
                if not pane:
                    logger.error(f"No active pane in window {window_id}")
                    return False

                pane.send_keys(text, enter=enter, literal=literal)
                return True

            except Exception as e:
                logger.error(f"Failed to send keys to window {window_id}: {e}")
                return False

        return await asyncio.to_thread(_sync_send_keys)

    async def kill_window(self, window_id: str) -> bool:
        """Kill a tmux window by its ID."""

        def _sync_kill() -> bool:
            session = self.get_session()
            if not session:
                return False
            try:
                window = session.windows.get(window_id=window_id)
                if not window:
                    return False
                window.kill()
                logger.info("Killed window %s", window_id)
                return True
            except Exception as e:
                logger.error(f"Failed to kill window {window_id}: {e}")
                return False

        return await asyncio.to_thread(_sync_kill)

    async def create_window(
        self,
        work_dir: str,
        window_name: str | None = None,
        start_claude: bool = True,
    ) -> tuple[bool, str, str]:
        """Create a new tmux window and optionally start Claude Code."""
        # Validate directory first
        path = Path(work_dir).expanduser().resolve()
        if not path.exists():
            return False, f"Directory does not exist: {work_dir}", ""
        if not path.is_dir():
            return False, f"Not a directory: {work_dir}", ""

        # Create window name, adding suffix if name already exists
        final_window_name = window_name if window_name else path.name

        # Check for existing window name
        base_name = final_window_name
        counter = 2
        while await self.find_window_by_name(final_window_name):
            final_window_name = f"{base_name}-{counter}"
            counter += 1

        # Create window in thread
        def _create_and_start() -> tuple[bool, str, str]:
            session = self.get_session()
            if not session:
                # Ensure session exists
                self.get_or_create_session()
                session = self.get_session()
            if not session:
                return False, "Failed to get or create tmux session", ""
            try:
                # Create new window
                window = session.new_window(
                    window_name=final_window_name,
                    start_directory=str(path),
                )

                # Start Claude Code if requested
                if start_claude:
                    pane = window.active_pane
                    if pane:
                        pane.send_keys(config.claude_command, enter=True)

                logger.info("Created window '%s' at %s", final_window_name, path)
                return True, f"Created window '{final_window_name}' at {path}", final_window_name

            except Exception as e:
                logger.error(f"Failed to create window: {e}")
                return False, f"Failed to create window: {e}", ""

        return await asyncio.to_thread(_create_and_start)
