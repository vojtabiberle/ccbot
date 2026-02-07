"""Application entry point — CLI dispatcher and bot bootstrap.

Handles two execution modes:
  1. `ccbot hook` — delegates to hook.hook_main() for Claude Code hook processing.
  2. Default — configures logging, initializes multiplexer session, and starts
     the Telegram bot polling loop via bot.create_bot().
"""

import logging
import sys


def main() -> None:
    """Main entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "hook":
        from .hook import hook_main

        hook_main()
        return

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.WARNING,
    )
    logging.getLogger("ccbot").setLevel(logging.DEBUG)
    logger = logging.getLogger(__name__)

    # Import after logging is configured — Config() validates env vars
    from .config import config
    from .multiplexer import get_mux

    logger.info("Allowed users: %s", config.allowed_users)
    logger.info("Claude projects path: %s", config.claude_projects_path)

    # Ensure multiplexer session exists
    mux = get_mux()
    mux.get_or_create_session()
    logger.info("Multiplexer session '%s' ready (backend=%s)", config.mux_session_name, config.multiplexer_backend)

    logger.info("Starting Telegram bot...")
    from .bot import create_bot

    application = create_bot()
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
