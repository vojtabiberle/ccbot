"""Application configuration — reads env vars and exposes a singleton.

Loads TELEGRAM_BOT_TOKEN, ALLOWED_USERS, multiplexer backend selection,
session naming, Claude paths, and monitoring intervals from environment
variables (with .env support).
The module-level `config` instance is imported by nearly every other module.

Key class: Config (singleton instantiated as `config`).
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class Config:
    """Application configuration loaded from environment variables."""

    def __init__(self) -> None:
        load_dotenv()

        self.telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN") or ""
        if not self.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

        allowed_users_str = os.getenv("ALLOWED_USERS", "")
        if not allowed_users_str:
            raise ValueError("ALLOWED_USERS environment variable is required")
        try:
            self.allowed_users: set[int] = {
                int(uid.strip()) for uid in allowed_users_str.split(",") if uid.strip()
            }
        except ValueError as e:
            raise ValueError(
                f"ALLOWED_USERS contains non-numeric value: {e}. "
                "Expected comma-separated Telegram user IDs."
            ) from e

        # Multiplexer backend selection (default: tmux for backward compat)
        self.multiplexer_backend: str = os.getenv("MULTIPLEXER", "tmux").lower()

        # Unified session naming (TMUX_SESSION_NAME still works as fallback)
        self.mux_session_name: str = os.getenv(
            "MUX_SESSION_NAME",
            os.getenv("TMUX_SESSION_NAME", "ccbot"),
        )
        self.mux_main_window_name: str = "__main__"

        # Keep old names as aliases for backward compatibility
        self.tmux_session_name = self.mux_session_name
        self.tmux_main_window_name = self.mux_main_window_name

        # Claude command to run in new windows
        self.claude_command = os.getenv("CLAUDE_COMMAND", "claude")

        # State file for persisting user subscriptions
        self.state_file = Path.home() / ".ccbot" / "state.json"

        # Claude Code session monitoring configuration
        self.claude_projects_path = Path.home() / ".claude" / "projects"
        self.monitor_poll_interval = float(os.getenv("MONITOR_POLL_INTERVAL", "2.0"))
        self.monitor_state_file = Path.home() / ".ccbot" / "monitor_state.json"

        # Hook-based session map file
        self.session_map_file = Path.home() / ".ccbot" / "session_map.json"

        # Display user messages in history and real-time notifications
        # When True, user messages are shown with a 👤 prefix
        self.show_user_messages = True

        logger.debug(
            "Config initialized: token=%s..., allowed_users=%d, "
            "multiplexer=%s, session=%s, state=%s",
            self.telegram_bot_token[:8],
            len(self.allowed_users),
            self.multiplexer_backend,
            self.mux_session_name,
            self.state_file,
        )

    def is_user_allowed(self, user_id: int) -> bool:
        """Check if a user is in the allowed list."""
        return user_id in self.allowed_users


config = Config()
