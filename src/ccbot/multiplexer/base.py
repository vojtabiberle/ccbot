"""Abstract base class for terminal multiplexer backends.

Defines the MultiplexerBackend ABC and MuxWindow dataclass that all backends
(tmux, Zellij) must implement. The ABC provides a unified interface for:
  - Session/window lifecycle: get_or_create_session, create_window, kill_window
  - Terminal I/O: capture_pane, send_keys
  - Window discovery: list_windows, find_window_by_name

MuxWindow is the backend-agnostic representation of a multiplexer window
(tmux window or Zellij tab).

Key class: MultiplexerBackend (ABC), MuxWindow (dataclass).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MuxWindow:
    """Information about a multiplexer window (tmux window or Zellij tab)."""

    window_id: str      # Backend-specific opaque ID (tmux: "@5", zellij: tab name)
    window_name: str    # Human-readable name
    cwd: str            # Current working directory


class MultiplexerBackend(ABC):
    """Abstract base for terminal multiplexer backends."""

    def __init__(self, session_name: str, main_window_name: str) -> None:
        self.session_name = session_name
        self.main_window_name = main_window_name

    @abstractmethod
    def get_or_create_session(self) -> None:
        """Ensure the multiplexer session exists.

        For tmux: creates the session if missing.
        For Zellij: verifies the session exists (raises on missing).
        """

    @abstractmethod
    async def list_windows(self) -> list[MuxWindow]:
        """List all windows in the session (excluding the main window)."""

    async def find_window_by_name(self, window_name: str) -> MuxWindow | None:
        """Find a window by its name.

        Default implementation filters list_windows(). Both backends share
        this logic.
        """
        windows = await self.list_windows()
        for window in windows:
            if window.window_name == window_name:
                return window
        logger.debug("Window not found: %s", window_name)
        return None

    @abstractmethod
    async def capture_pane(self, window_id: str, with_ansi: bool = False) -> str | None:
        """Capture the visible text content of a window's active pane.

        Args:
            window_id: Backend-specific window identifier.
            with_ansi: If True, capture with ANSI color codes (not all
                       backends support this).

        Returns:
            The captured text, or None on failure.
        """

    @abstractmethod
    async def send_keys(
        self, window_id: str, text: str, enter: bool = True, literal: bool = True,
    ) -> bool:
        """Send keys to a specific window.

        Args:
            window_id: Backend-specific window identifier.
            text: Text to send.
            enter: Whether to press Enter after the text.
            literal: If True, send text literally. If False, interpret special
                     keys like "Up", "Down", "Escape", "Enter".

        Returns:
            True if successful, False otherwise.
        """

    @abstractmethod
    async def kill_window(self, window_id: str) -> bool:
        """Kill a window by its ID."""

    @abstractmethod
    async def create_window(
        self,
        work_dir: str,
        window_name: str | None = None,
        start_claude: bool = True,
    ) -> tuple[bool, str, str]:
        """Create a new window and optionally start Claude Code.

        Args:
            work_dir: Working directory for the new window.
            window_name: Optional window name (defaults to directory name).
            start_claude: Whether to start the claude command.

        Returns:
            Tuple of (success, message, window_name).
        """
