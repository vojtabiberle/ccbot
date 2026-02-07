"""Terminal status line polling for thread-bound windows.

Provides background polling of terminal status lines for all active users:
  - Detects Claude Code status (working, waiting, etc.)
  - Detects interactive UIs (permission prompts) not triggered via JSONL
  - Detects idle suggestion prompts and surfaces them in Telegram
  - Updates status messages in Telegram
  - Polls thread_bindings (each topic = one window)
  - Periodically probes topic existence via unpin_all_forum_topic_messages
    (silent no-op when no pins); cleans up deleted topics (kills tmux window
    + unbinds thread)

Key components:
  - STATUS_POLL_INTERVAL: Polling frequency (1 second)
  - TOPIC_CHECK_INTERVAL: Topic existence probe frequency (60 seconds)
  - status_poll_loop: Background polling task
  - update_status_message: Poll and enqueue status updates
  - clear_suggestion / get_suggestion_text: Suggestion message lifecycle
"""

import asyncio
import logging
import time

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

from ..session import session_manager
from ..terminal_parser import is_interactive_ui, parse_status_line, parse_suggestion
from ..multiplexer import get_mux
from .callback_data import CB_SUGGESTION_SEND
from .interactive_ui import (
    clear_interactive_msg,
    get_interactive_msg_id,
    get_interactive_window,
    handle_interactive_ui,
)
from .cleanup import clear_topic_state
from .message_queue import enqueue_status_update, get_message_queue
from .message_sender import rate_limit_send_message

logger = logging.getLogger(__name__)

# Status polling interval
STATUS_POLL_INTERVAL = 1.0  # seconds - faster response (rate limiting at send layer)

# Topic existence probe interval
TOPIC_CHECK_INTERVAL = 60.0  # seconds

# Suggestion message tracking: (chat_id, thread_id) -> message_id / text
_suggestion_msgs: dict[tuple[int, int], int] = {}
_suggestion_text: dict[tuple[int, int], str] = {}


def _ikey(chat_id: int, thread_id: int | None) -> tuple[int, int]:
    """Build the dict key for suggestion state."""
    return (chat_id, thread_id or 0)


async def _send_suggestion_msg(
    bot: Bot,
    chat_id: int,
    window_name: str,
    text: str,
    thread_id: int | None,
) -> None:
    """Send (or replace) the suggestion Telegram message."""
    ikey = _ikey(chat_id, thread_id)

    # Delete old message if present
    old_msg_id = _suggestion_msgs.get(ikey)
    if old_msg_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=old_msg_id)
        except Exception:
            pass

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "✅ Send",
            callback_data=f"{CB_SUGGESTION_SEND}{window_name}"[:64],
        ),
    ]])
    msg = await rate_limit_send_message(
        bot,
        chat_id,
        f"❓ {text}",
        message_thread_id=thread_id,
        reply_markup=keyboard,
    )
    if msg:
        _suggestion_msgs[ikey] = msg.message_id
        _suggestion_text[ikey] = text


async def clear_suggestion(
    chat_id: int, bot: Bot, thread_id: int | None = None,
) -> None:
    """Delete the suggestion message and clear tracking state."""
    ikey = _ikey(chat_id, thread_id)
    msg_id = _suggestion_msgs.pop(ikey, None)
    _suggestion_text.pop(ikey, None)
    if msg_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass


def get_suggestion_text(
    chat_id: int, thread_id: int | None = None,
) -> str | None:
    """Return the stored suggestion text for a chat/thread, or None."""
    return _suggestion_text.get(_ikey(chat_id, thread_id))


async def update_status_message(
    bot: Bot,
    chat_id: int,
    window_name: str,
    thread_id: int | None = None,
) -> None:
    """Poll terminal and enqueue status update for chat's active window.

    Also detects permission prompt UIs (not triggered via JSONL) and enters
    interactive mode when found.
    """
    w = await get_mux().find_window_by_name(window_name)
    if not w:
        # Window gone, enqueue clear
        await enqueue_status_update(bot, chat_id, window_name, None, thread_id=thread_id)
        return

    pane_text = await get_mux().capture_pane(w.window_id)
    if not pane_text:
        # Transient capture failure - keep existing status message
        return

    interactive_window = get_interactive_window(chat_id, thread_id)
    should_check_new_ui = True

    if interactive_window == window_name:
        # Chat is in interactive mode for THIS window
        if is_interactive_ui(pane_text):
            # If interactive mode is set but no message sent yet, the JSONL
            # handler is still processing (sleeping before capture).  Skip
            # this cycle to avoid sending a duplicate message.
            if not get_interactive_msg_id(chat_id, thread_id):
                return
            # Interactive UI still showing — refresh in case content changed
            # (e.g. multi-question AskUserQuestion advancing to next question)
            await handle_interactive_ui(bot, chat_id, window_name, thread_id)
            return
        # Interactive UI gone — clear interactive mode, fall through to status check.
        # Don't re-check for new UI this cycle (the old one just disappeared).
        await clear_interactive_msg(chat_id, bot, thread_id)
        should_check_new_ui = False
    elif interactive_window is not None:
        # Chat is in interactive mode for a DIFFERENT window (window switched)
        # Clear stale interactive mode
        await clear_interactive_msg(chat_id, bot, thread_id)

    # Check for permission prompt (interactive UI not triggered via JSONL)
    if should_check_new_ui and is_interactive_ui(pane_text):
        await handle_interactive_ui(bot, chat_id, window_name, thread_id)
        return

    # Suggestion prompt detection
    ikey = _ikey(chat_id, thread_id)
    suggestion = parse_suggestion(pane_text)
    if suggestion:
        if _suggestion_text.get(ikey) != suggestion:
            await _send_suggestion_msg(bot, chat_id, window_name, suggestion, thread_id)
        # Suggestion is showing — skip status line check
        return
    elif ikey in _suggestion_msgs:
        # Suggestion gone (Claude started working) — clean up
        await clear_suggestion(chat_id, bot, thread_id)

    # Normal status line check
    status_line = parse_status_line(pane_text)

    if status_line:
        await enqueue_status_update(
            bot, chat_id, window_name, status_line, thread_id=thread_id,
        )
    # If no status line, keep existing status message (don't clear on transient state)


async def status_poll_loop(bot: Bot) -> None:
    """Background task to poll terminal status for all thread-bound windows."""
    logger.info("Status polling started (interval: %ss)", STATUS_POLL_INTERVAL)
    last_topic_check = 0.0
    while True:
        try:
            # Periodic topic existence probe
            now = time.monotonic()
            if now - last_topic_check >= TOPIC_CHECK_INTERVAL:
                last_topic_check = now
                for chat_id, thread_id, wname in list(
                    session_manager.iter_thread_bindings()
                ):
                    try:
                        await bot.unpin_all_forum_topic_messages(
                            chat_id=chat_id,
                            message_thread_id=thread_id,
                        )
                    except BadRequest as e:
                        if "Topic_id_invalid" in str(e):
                            # Topic deleted — kill window, unbind, and clean up state
                            w = await get_mux().find_window_by_name(wname)
                            if w:
                                await get_mux().kill_window(w.window_id)
                            session_manager.unbind_thread(chat_id, thread_id)
                            await clear_topic_state(chat_id, thread_id, bot)
                            logger.info(
                                "Topic deleted: killed window '%s' and "
                                "unbound thread %d for chat %d",
                                wname,
                                thread_id,
                                chat_id,
                            )
                        else:
                            logger.debug(
                                "Topic probe error for %s: %s", wname, e,
                            )
                    except Exception as e:
                        logger.debug(
                            "Topic probe error for %s: %s", wname, e,
                        )

            for chat_id, thread_id, wname in list(
                session_manager.iter_thread_bindings()
            ):
                try:
                    # Clean up stale bindings (window no longer exists)
                    w = await get_mux().find_window_by_name(wname)
                    if not w:
                        session_manager.unbind_thread(chat_id, thread_id)
                        await clear_topic_state(chat_id, thread_id, bot)
                        logger.info(
                            f"Cleaned up stale binding: chat={chat_id} "
                            f"thread={thread_id} window={wname}"
                        )
                        continue
                    queue = get_message_queue(chat_id)
                    if queue and not queue.empty():
                        continue
                    await update_status_message(
                        bot, chat_id, wname, thread_id=thread_id,
                    )
                except Exception as e:
                    logger.debug(
                        f"Status update error for chat {chat_id} "
                        f"thread {thread_id}: {e}"
                    )
        except Exception as e:
            logger.error(f"Status poll loop error: {e}")

        await asyncio.sleep(STATUS_POLL_INTERVAL)
