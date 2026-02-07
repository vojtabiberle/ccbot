"""Tests for /bind and /unbind command handlers and CB_BIND_SELECT callback."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ccbot.bot import bind_command, unbind_command, callback_handler
from ccbot.handlers.callback_data import CB_BIND_SELECT
from ccbot.multiplexer.base import MuxWindow


CHAT_ID = -1001234567890
THREAD_ID = 42
USER_ID = 12345


def _make_update(thread_id: int | None = THREAD_ID, user_id: int = USER_ID):
    """Build a mock Update with message in a named topic."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    update.effective_chat = MagicMock()
    update.effective_chat.id = CHAT_ID
    update.message = MagicMock()
    update.message.message_thread_id = thread_id
    update.callback_query = None
    return update


def _make_callback_update(
    data: str, thread_id: int | None = THREAD_ID, user_id: int = USER_ID,
):
    """Build a mock Update with a callback query."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    update.effective_chat = MagicMock()
    update.effective_chat.id = CHAT_ID
    update.message = None

    query = MagicMock()
    query.data = data
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.message_thread_id = thread_id
    update.callback_query = query
    return update


def _make_context():
    """Build a mock context."""
    ctx = MagicMock()
    ctx.user_data = {}
    ctx.bot = AsyncMock()
    ctx.bot.edit_forum_topic = AsyncMock()
    return ctx


def _patch_auth(allowed: bool = True):
    """Patch is_user_allowed to control authorization."""
    return patch("ccbot.bot.is_user_allowed", return_value=allowed)


# ── /bind command ──────────────────────────────────────────────────────


class TestBindCommand:
    @pytest.mark.asyncio
    async def test_not_in_topic(self):
        """Should reject when not in a named topic (thread_id is None)."""
        update = _make_update(thread_id=None)
        ctx = _make_context()
        with (
            _patch_auth(),
            patch("ccbot.bot.safe_reply", new_callable=AsyncMock) as mock_reply,
        ):
            await bind_command(update, ctx)
            mock_reply.assert_called_once()
            assert "named topic" in mock_reply.call_args[0][1]

    @pytest.mark.asyncio
    async def test_already_bound(self):
        """Should reject when topic is already bound to a window."""
        update = _make_update()
        ctx = _make_context()
        with (
            _patch_auth(),
            patch("ccbot.bot.safe_reply", new_callable=AsyncMock) as mock_reply,
            patch("ccbot.bot.session_manager") as mock_sm,
        ):
            mock_sm.get_window_for_thread.return_value = "my-window"
            await bind_command(update, ctx)
            mock_reply.assert_called_once()
            assert "already bound" in mock_reply.call_args[0][1]

    @pytest.mark.asyncio
    async def test_no_unbound_windows(self):
        """Should show message when all windows are already bound."""
        update = _make_update()
        ctx = _make_context()
        with (
            _patch_auth(),
            patch("ccbot.bot.safe_reply", new_callable=AsyncMock) as mock_reply,
            patch("ccbot.bot.get_mux") as mock_mux,
            patch("ccbot.bot.session_manager") as mock_sm,
        ):
            mock_sm.get_window_for_thread.return_value = None
            mock_sm.load_session_map = AsyncMock()
            mock_mux_inst = MagicMock()
            mock_mux_inst.list_windows = AsyncMock(return_value=[
                MuxWindow(window_id="@1", window_name="proj", cwd="/home/user/proj"),
            ])
            mock_mux.return_value = mock_mux_inst
            mock_sm.get_thread_for_window.return_value = 99  # already bound

            await bind_command(update, ctx)
            mock_reply.assert_called_once()
            assert "No unbound windows" in mock_reply.call_args[0][1]

    @pytest.mark.asyncio
    async def test_shows_unbound_windows(self):
        """Should show inline keyboard with unbound windows."""
        update = _make_update()
        ctx = _make_context()
        with (
            _patch_auth(),
            patch("ccbot.bot.safe_reply", new_callable=AsyncMock) as mock_reply,
            patch("ccbot.bot.get_mux") as mock_mux,
            patch("ccbot.bot.session_manager") as mock_sm,
        ):
            mock_sm.get_window_for_thread.return_value = None
            mock_sm.load_session_map = AsyncMock()
            mock_mux_inst = MagicMock()
            mock_mux_inst.list_windows = AsyncMock(return_value=[
                MuxWindow(window_id="@1", window_name="proj-a", cwd="/home/proj-a"),
                MuxWindow(window_id="@2", window_name="proj-b", cwd="/home/proj-b"),
            ])
            mock_mux.return_value = mock_mux_inst
            mock_sm.get_thread_for_window.return_value = None

            await bind_command(update, ctx)
            mock_reply.assert_called_once()
            assert "Select a window" in mock_reply.call_args[0][1]
            keyboard = mock_reply.call_args[1]["reply_markup"]
            buttons = keyboard.inline_keyboard
            assert len(buttons) == 2
            assert "proj-a" in buttons[0][0].text
            assert "proj-b" in buttons[1][0].text

    @pytest.mark.asyncio
    async def test_filters_bound_windows(self):
        """Should only show windows not already bound to a topic."""
        update = _make_update()
        ctx = _make_context()
        with (
            _patch_auth(),
            patch("ccbot.bot.safe_reply", new_callable=AsyncMock) as mock_reply,
            patch("ccbot.bot.get_mux") as mock_mux,
            patch("ccbot.bot.session_manager") as mock_sm,
        ):
            mock_sm.get_window_for_thread.return_value = None
            mock_sm.load_session_map = AsyncMock()
            mock_mux_inst = MagicMock()
            mock_mux_inst.list_windows = AsyncMock(return_value=[
                MuxWindow(window_id="@1", window_name="bound-win", cwd="/a"),
                MuxWindow(window_id="@2", window_name="free-win", cwd="/b"),
            ])
            mock_mux.return_value = mock_mux_inst

            def thread_for_window(_cid, wname):
                if wname == "bound-win":
                    return 99
                return None
            mock_sm.get_thread_for_window.side_effect = thread_for_window

            await bind_command(update, ctx)
            keyboard = mock_reply.call_args[1]["reply_markup"]
            buttons = keyboard.inline_keyboard
            assert len(buttons) == 1
            assert "free-win" in buttons[0][0].text

    @pytest.mark.asyncio
    async def test_unauthorized_user(self):
        """Should silently return for unauthorized users."""
        update = _make_update()
        ctx = _make_context()
        with (
            _patch_auth(allowed=False),
            patch("ccbot.bot.safe_reply", new_callable=AsyncMock) as mock_reply,
        ):
            await bind_command(update, ctx)
            mock_reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_window_without_cwd(self):
        """Window label should omit cwd when empty."""
        update = _make_update()
        ctx = _make_context()
        with (
            _patch_auth(),
            patch("ccbot.bot.safe_reply", new_callable=AsyncMock) as mock_reply,
            patch("ccbot.bot.get_mux") as mock_mux,
            patch("ccbot.bot.session_manager") as mock_sm,
        ):
            mock_sm.get_window_for_thread.return_value = None
            mock_sm.load_session_map = AsyncMock()
            mock_mux_inst = MagicMock()
            mock_mux_inst.list_windows = AsyncMock(return_value=[
                MuxWindow(window_id="@1", window_name="no-cwd", cwd=""),
            ])
            mock_mux.return_value = mock_mux_inst
            mock_sm.get_thread_for_window.return_value = None

            await bind_command(update, ctx)
            keyboard = mock_reply.call_args[1]["reply_markup"]
            label = keyboard.inline_keyboard[0][0].text
            assert label == "no-cwd"
            assert "(" not in label


# ── /unbind command ────────────────────────────────────────────────────


class TestUnbindCommand:
    @pytest.mark.asyncio
    async def test_not_in_topic(self):
        """Should reject when not in a named topic."""
        update = _make_update(thread_id=None)
        ctx = _make_context()
        with (
            _patch_auth(),
            patch("ccbot.bot.safe_reply", new_callable=AsyncMock) as mock_reply,
        ):
            await unbind_command(update, ctx)
            mock_reply.assert_called_once()
            assert "named topic" in mock_reply.call_args[0][1]

    @pytest.mark.asyncio
    async def test_not_bound(self):
        """Should reject when topic has no binding."""
        update = _make_update()
        ctx = _make_context()
        with (
            _patch_auth(),
            patch("ccbot.bot.safe_reply", new_callable=AsyncMock) as mock_reply,
            patch("ccbot.bot.session_manager") as mock_sm,
        ):
            mock_sm.get_window_for_thread.return_value = None
            await unbind_command(update, ctx)
            mock_reply.assert_called_once()
            assert "No session bound" in mock_reply.call_args[0][1]

    @pytest.mark.asyncio
    async def test_unbinds_successfully(self):
        """Should unbind thread and confirm, leaving window running."""
        update = _make_update()
        ctx = _make_context()
        with (
            _patch_auth(),
            patch("ccbot.bot.safe_reply", new_callable=AsyncMock) as mock_reply,
            patch("ccbot.bot.clear_topic_state", new_callable=AsyncMock) as mock_clear,
            patch("ccbot.bot.session_manager") as mock_sm,
        ):
            mock_sm.get_window_for_thread.return_value = "my-window"
            await unbind_command(update, ctx)
            mock_sm.unbind_thread.assert_called_once_with(CHAT_ID, THREAD_ID)
            mock_clear.assert_called_once_with(
                CHAT_ID, THREAD_ID, ctx.bot, ctx.user_data,
            )
            mock_reply.assert_called_once()
            assert "Unbound" in mock_reply.call_args[0][1]
            assert "still running" in mock_reply.call_args[0][1]

    @pytest.mark.asyncio
    async def test_unauthorized_user(self):
        """Should silently return for unauthorized users."""
        update = _make_update()
        ctx = _make_context()
        with (
            _patch_auth(allowed=False),
            patch("ccbot.bot.safe_reply", new_callable=AsyncMock) as mock_reply,
        ):
            await unbind_command(update, ctx)
            mock_reply.assert_not_called()


# ── CB_BIND_SELECT callback ───────────────────────────────────────────


class TestBindSelectCallback:
    @pytest.mark.asyncio
    async def test_successful_bind(self):
        """Should bind thread to window, rename topic, and confirm."""
        update = _make_callback_update(f"{CB_BIND_SELECT}proj")
        ctx = _make_context()
        with (
            _patch_auth(),
            patch("ccbot.bot.safe_edit", new_callable=AsyncMock) as mock_edit,
            patch("ccbot.bot.get_mux") as mock_mux,
            patch("ccbot.bot.session_manager") as mock_sm,
        ):
            mock_sm.get_window_for_thread.return_value = None
            mock_sm.get_thread_for_window.return_value = None
            mock_mux_inst = MagicMock()
            mock_mux_inst.find_window_by_name = AsyncMock(
                return_value=MuxWindow(window_id="@1", window_name="proj", cwd="/proj")
            )
            mock_mux.return_value = mock_mux_inst

            await callback_handler(update, ctx)

            mock_sm.bind_thread.assert_called_once_with(CHAT_ID, THREAD_ID, "proj")
            ctx.bot.edit_forum_topic.assert_called_once_with(
                chat_id=CHAT_ID, message_thread_id=THREAD_ID, name="proj",
            )
            mock_edit.assert_called_once()
            assert "Bound" in mock_edit.call_args[0][1]
            update.callback_query.answer.assert_called_once_with("Bound")

    @pytest.mark.asyncio
    async def test_topic_already_bound(self):
        """Should reject if topic became bound between command and callback."""
        update = _make_callback_update(f"{CB_BIND_SELECT}proj")
        ctx = _make_context()
        with (
            _patch_auth(),
            patch("ccbot.bot.safe_edit", new_callable=AsyncMock) as mock_edit,
            patch("ccbot.bot.session_manager") as mock_sm,
        ):
            mock_sm.get_window_for_thread.return_value = "other-window"

            await callback_handler(update, ctx)

            mock_sm.bind_thread.assert_not_called()
            mock_edit.assert_called_once()
            assert "already bound" in mock_edit.call_args[0][1]

    @pytest.mark.asyncio
    async def test_window_gone(self):
        """Should reject if window disappeared before callback."""
        update = _make_callback_update(f"{CB_BIND_SELECT}proj")
        ctx = _make_context()
        with (
            _patch_auth(),
            patch("ccbot.bot.safe_edit", new_callable=AsyncMock) as mock_edit,
            patch("ccbot.bot.get_mux") as mock_mux,
            patch("ccbot.bot.session_manager") as mock_sm,
        ):
            mock_sm.get_window_for_thread.return_value = None
            mock_mux_inst = MagicMock()
            mock_mux_inst.find_window_by_name = AsyncMock(return_value=None)
            mock_mux.return_value = mock_mux_inst

            await callback_handler(update, ctx)

            mock_sm.bind_thread.assert_not_called()
            mock_edit.assert_called_once()
            assert "no longer exists" in mock_edit.call_args[0][1]

    @pytest.mark.asyncio
    async def test_window_bound_elsewhere(self):
        """Should reject if window got bound to another topic."""
        update = _make_callback_update(f"{CB_BIND_SELECT}proj")
        ctx = _make_context()
        with (
            _patch_auth(),
            patch("ccbot.bot.safe_edit", new_callable=AsyncMock) as mock_edit,
            patch("ccbot.bot.get_mux") as mock_mux,
            patch("ccbot.bot.session_manager") as mock_sm,
        ):
            mock_sm.get_window_for_thread.return_value = None
            mock_sm.get_thread_for_window.return_value = 999
            mock_mux_inst = MagicMock()
            mock_mux_inst.find_window_by_name = AsyncMock(
                return_value=MuxWindow(window_id="@1", window_name="proj", cwd="/proj")
            )
            mock_mux.return_value = mock_mux_inst

            await callback_handler(update, ctx)

            mock_sm.bind_thread.assert_not_called()
            mock_edit.assert_called_once()
            assert "already bound to another" in mock_edit.call_args[0][1]

    @pytest.mark.asyncio
    async def test_not_in_topic(self):
        """Should answer with alert when thread_id is None."""
        update = _make_callback_update(f"{CB_BIND_SELECT}proj", thread_id=None)
        ctx = _make_context()
        with _patch_auth():
            await callback_handler(update, ctx)
            update.callback_query.answer.assert_called_once_with(
                "Use this in a named topic", show_alert=True,
            )

    @pytest.mark.asyncio
    async def test_rename_topic_failure_non_fatal(self):
        """Topic rename failure should not prevent binding."""
        update = _make_callback_update(f"{CB_BIND_SELECT}proj")
        ctx = _make_context()
        ctx.bot.edit_forum_topic = AsyncMock(side_effect=Exception("Telegram error"))
        with (
            _patch_auth(),
            patch("ccbot.bot.safe_edit", new_callable=AsyncMock) as mock_edit,
            patch("ccbot.bot.get_mux") as mock_mux,
            patch("ccbot.bot.session_manager") as mock_sm,
        ):
            mock_sm.get_window_for_thread.return_value = None
            mock_sm.get_thread_for_window.return_value = None
            mock_mux_inst = MagicMock()
            mock_mux_inst.find_window_by_name = AsyncMock(
                return_value=MuxWindow(window_id="@1", window_name="proj", cwd="/proj")
            )
            mock_mux.return_value = mock_mux_inst

            await callback_handler(update, ctx)

            mock_sm.bind_thread.assert_called_once_with(CHAT_ID, THREAD_ID, "proj")
            mock_edit.assert_called_once()
            assert "Bound" in mock_edit.call_args[0][1]
