"""Tests for ZellijBackend — mocked subprocess calls."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import pytest

from ccbot.multiplexer.zellij_backend import ZellijBackend
from ccbot.multiplexer.base import MuxWindow


@pytest.fixture
def backend() -> ZellijBackend:
    return ZellijBackend("ccbot", "__main__")


def _make_proc(rc: int = 0, stdout: str = "", stderr: str = "") -> AsyncMock:
    """Create a mock process with communicate() returning (stdout, stderr)."""
    proc = AsyncMock()
    proc.returncode = rc
    proc.communicate = AsyncMock(
        return_value=(stdout.encode(), stderr.encode())
    )
    return proc


# ── get_or_create_session ────────────────────────────────────────────────


class TestGetOrCreateSession:
    def test_session_exists(self, backend: ZellijBackend):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="ccbot\nother\n", returncode=0)
            backend.get_or_create_session()  # Should not raise

    def test_session_missing_raises(self, backend: ZellijBackend):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="other-session\n", returncode=0)
            with pytest.raises(RuntimeError, match="not found"):
                backend.get_or_create_session()

    def test_empty_sessions_raises(self, backend: ZellijBackend):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            with pytest.raises(RuntimeError, match="not found"):
                backend.get_or_create_session()


# ── list_windows ─────────────────────────────────────────────────────────


class TestListWindows:
    @pytest.mark.asyncio
    async def test_lists_tabs(self, backend: ZellijBackend):
        """Should parse tab names and cwds from Zellij CLI output."""
        tab_names_output = "proj-a\nproj-b\n__main__\n"
        dump_layout_output = (
            'tab name="proj-a" { pane cwd="/home/user/proj-a" }\n'
            'tab name="proj-b" { pane cwd="/home/user/proj-b" }\n'
            'tab name="__main__" { pane cwd="/home/user" }\n'
        )

        calls = [
            _make_proc(0, tab_names_output),
            _make_proc(0, dump_layout_output),
        ]

        with patch("asyncio.create_subprocess_exec", side_effect=calls):
            windows = await backend.list_windows()

        assert len(windows) == 2
        assert windows[0].window_name == "proj-a"
        assert windows[0].cwd == "/home/user/proj-a"
        assert windows[1].window_name == "proj-b"

    @pytest.mark.asyncio
    async def test_query_fails(self, backend: ZellijBackend):
        """Returns empty list when query-tab-names fails."""
        with patch(
            "asyncio.create_subprocess_exec",
            return_value=_make_proc(1, "", "error"),
        ):
            windows = await backend.list_windows()
        assert windows == []

    @pytest.mark.asyncio
    async def test_no_cwds(self, backend: ZellijBackend):
        """Tabs with no parseable cwd get empty string."""
        calls = [
            _make_proc(0, "proj\n"),
            _make_proc(1, "", "dump-layout failed"),
        ]
        with patch("asyncio.create_subprocess_exec", side_effect=calls):
            windows = await backend.list_windows()
        assert len(windows) == 1
        assert windows[0].cwd == ""


# ── capture_pane ─────────────────────────────────────────────────────────


class TestCapturePanePlain:
    @pytest.mark.asyncio
    async def test_captures_text(self, backend: ZellijBackend, tmp_path: Path):
        """Should navigate to tab, dump-screen to file, read and return."""
        dump_file_content = "Hello from Zellij\nLine 2\n"

        calls = [
            _make_proc(0),  # go-to-tab-name
            _make_proc(0),  # dump-screen
        ]

        with (
            patch("asyncio.create_subprocess_exec", side_effect=calls),
            patch("ccbot.multiplexer.zellij_backend.Path.read_text", return_value=dump_file_content),
            patch("os.unlink"),
        ):
            result = await backend.capture_pane("proj")

        assert result == dump_file_content

    @pytest.mark.asyncio
    async def test_navigate_fails(self, backend: ZellijBackend):
        """Returns None when tab navigation fails."""
        with patch(
            "asyncio.create_subprocess_exec",
            return_value=_make_proc(1, "", "no such tab"),
        ):
            result = await backend.capture_pane("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_ansi_fallback_warning(self, backend: ZellijBackend, caplog):
        """with_ansi=True logs a warning about plain text fallback."""
        import ccbot.multiplexer.zellij_backend as zmod
        original = zmod._ansi_warned
        zmod._ansi_warned = False

        calls = [
            _make_proc(0),  # go-to-tab-name
            _make_proc(0),  # dump-screen
        ]
        try:
            with (
                patch("asyncio.create_subprocess_exec", side_effect=calls),
                patch("ccbot.multiplexer.zellij_backend.Path.read_text", return_value="text"),
                patch("os.unlink"),
            ):
                result = await backend.capture_pane("proj", with_ansi=True)
            assert result == "text"
            assert zmod._ansi_warned is True
        finally:
            zmod._ansi_warned = original


# ── send_keys ────────────────────────────────────────────────────────────


class TestSendKeys:
    @pytest.mark.asyncio
    async def test_literal_text_with_enter(self, backend: ZellijBackend):
        """Should navigate, write-chars, wait, then write Enter byte."""
        calls = [
            _make_proc(0),  # go-to-tab-name
            _make_proc(0),  # write-chars "hello"
            _make_proc(0),  # write 13 (Enter)
        ]
        with patch("asyncio.create_subprocess_exec", side_effect=calls) as mock_exec:
            result = await backend.send_keys("proj", "hello", enter=True, literal=True)

        assert result is True
        # Verify the calls: go-to-tab-name, write-chars, write 13
        assert mock_exec.call_count == 3
        # Check write-chars call
        args2 = mock_exec.call_args_list[1][0]
        assert "write-chars" in args2
        assert "hello" in args2
        # Check Enter
        args3 = mock_exec.call_args_list[2][0]
        assert "write" in args3
        assert "13" in args3

    @pytest.mark.asyncio
    async def test_literal_text_no_enter(self, backend: ZellijBackend):
        """Should write-chars but not send Enter."""
        calls = [
            _make_proc(0),  # go-to-tab-name
            _make_proc(0),  # write-chars
        ]
        with patch("asyncio.create_subprocess_exec", side_effect=calls) as mock_exec:
            result = await backend.send_keys("proj", "text", enter=False, literal=True)

        assert result is True
        assert mock_exec.call_count == 2

    @pytest.mark.asyncio
    async def test_special_key_escape(self, backend: ZellijBackend):
        """literal=False with 'Escape' sends write 27."""
        calls = [
            _make_proc(0),  # go-to-tab-name
            _make_proc(0),  # write 27
        ]
        with patch("asyncio.create_subprocess_exec", side_effect=calls) as mock_exec:
            result = await backend.send_keys("proj", "Escape", enter=False, literal=False)

        assert result is True
        args2 = mock_exec.call_args_list[1][0]
        assert "write" in args2
        assert "27" in args2

    @pytest.mark.asyncio
    async def test_special_key_up(self, backend: ZellijBackend):
        """literal=False with 'Up' sends ANSI escape sequence."""
        calls = [
            _make_proc(0),  # go-to-tab-name
            _make_proc(0),  # write-chars \x1b[A
        ]
        with patch("asyncio.create_subprocess_exec", side_effect=calls) as mock_exec:
            result = await backend.send_keys("proj", "Up", enter=False, literal=False)

        assert result is True
        args2 = mock_exec.call_args_list[1][0]
        assert "write-chars" in args2
        assert "\x1b[A" in args2

    @pytest.mark.asyncio
    async def test_special_key_down(self, backend: ZellijBackend):
        calls = [_make_proc(0), _make_proc(0)]
        with patch("asyncio.create_subprocess_exec", side_effect=calls) as mock_exec:
            result = await backend.send_keys("proj", "Down", enter=False, literal=False)
        assert result is True
        assert "\x1b[B" in mock_exec.call_args_list[1][0]

    @pytest.mark.asyncio
    async def test_special_key_enter(self, backend: ZellijBackend):
        calls = [_make_proc(0), _make_proc(0)]
        with patch("asyncio.create_subprocess_exec", side_effect=calls) as mock_exec:
            result = await backend.send_keys("proj", "Enter", enter=False, literal=False)
        assert result is True
        args2 = mock_exec.call_args_list[1][0]
        assert "write" in args2
        assert "13" in args2

    @pytest.mark.asyncio
    async def test_navigate_fails(self, backend: ZellijBackend):
        """Returns False when tab navigation fails."""
        with patch(
            "asyncio.create_subprocess_exec",
            return_value=_make_proc(1, "", "no tab"),
        ):
            result = await backend.send_keys("bad-tab", "hello")
        assert result is False


# ── kill_window ──────────────────────────────────────────────────────────


class TestKillWindow:
    @pytest.mark.asyncio
    async def test_kills_tab(self, backend: ZellijBackend):
        calls = [_make_proc(0), _make_proc(0)]  # go-to + close-tab
        with patch("asyncio.create_subprocess_exec", side_effect=calls):
            result = await backend.kill_window("proj")
        assert result is True

    @pytest.mark.asyncio
    async def test_navigate_fails(self, backend: ZellijBackend):
        with patch(
            "asyncio.create_subprocess_exec",
            return_value=_make_proc(1),
        ):
            result = await backend.kill_window("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_close_fails(self, backend: ZellijBackend):
        calls = [_make_proc(0), _make_proc(1)]
        with patch("asyncio.create_subprocess_exec", side_effect=calls):
            result = await backend.kill_window("proj")
        assert result is False


# ── create_window ────────────────────────────────────────────────────────


class TestCreateWindow:
    @pytest.mark.asyncio
    async def test_creates_tab(self, backend: ZellijBackend, tmp_path: Path):
        work_dir = tmp_path / "myproject"
        work_dir.mkdir()

        calls = [
            _make_proc(1),  # list_windows -> query-tab-names (no existing tabs)
            _make_proc(0),  # new-tab
            _make_proc(0),  # write-chars (claude command)
            _make_proc(0),  # write 13 (Enter)
        ]
        with patch("asyncio.create_subprocess_exec", side_effect=calls):
            success, msg, name = await backend.create_window(str(work_dir))

        assert success is True
        assert name == "myproject"
        assert "Created" in msg

    @pytest.mark.asyncio
    async def test_invalid_directory(self, backend: ZellijBackend, tmp_path: Path):
        success, msg, name = await backend.create_window(str(tmp_path / "nonexistent"))
        assert success is False
        assert "does not exist" in msg

    @pytest.mark.asyncio
    async def test_not_a_directory(self, backend: ZellijBackend, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        success, msg, name = await backend.create_window(str(f))
        assert success is False
        assert "Not a directory" in msg

    @pytest.mark.asyncio
    async def test_auto_suffix_dedup(self, backend: ZellijBackend, tmp_path: Path):
        """Should add -2 suffix when name already exists."""
        work_dir = tmp_path / "proj"
        work_dir.mkdir()

        calls = [
            # First find_window_by_name("proj") -> list_windows finds "proj"
            _make_proc(0, "proj\n"),       # query-tab-names
            _make_proc(0, 'tab name="proj" { pane cwd="/tmp" }\n'),  # dump-layout
            # Second find_window_by_name("proj-2") -> list_windows, no match
            _make_proc(0, "proj\n"),       # query-tab-names
            _make_proc(0, 'tab name="proj" { pane cwd="/tmp" }\n'),  # dump-layout
            # create new-tab
            _make_proc(0),                 # new-tab
            _make_proc(0),                 # write-chars
            _make_proc(0),                 # write 13
        ]
        with patch("asyncio.create_subprocess_exec", side_effect=calls):
            success, msg, name = await backend.create_window(str(work_dir))

        assert success is True
        assert name == "proj-2"

    @pytest.mark.asyncio
    async def test_no_claude_start(self, backend: ZellijBackend, tmp_path: Path):
        work_dir = tmp_path / "proj"
        work_dir.mkdir()

        calls = [
            _make_proc(1),  # list_windows -> query-tab-names fails
            _make_proc(0),  # new-tab
        ]
        with patch("asyncio.create_subprocess_exec", side_effect=calls):
            success, msg, name = await backend.create_window(
                str(work_dir), start_claude=False,
            )

        assert success is True
        assert name == "proj"


# ── Lock serialization ───────────────────────────────────────────────────


class TestLockSerialization:
    @pytest.mark.asyncio
    async def test_concurrent_operations_serialized(self, backend: ZellijBackend):
        """Verify that concurrent operations are serialized via the lock."""
        order: list[str] = []

        async def mock_exec(*args, **kwargs):
            proc = _make_proc(0, "")
            # Track ordering via action name
            for a in args:
                if a in ("go-to-tab-name", "dump-screen", "close-tab"):
                    order.append(a)
                    break
            return proc

        with (
            patch("asyncio.create_subprocess_exec", side_effect=mock_exec),
            patch("ccbot.multiplexer.zellij_backend.Path.read_text", return_value="text"),
            patch("os.unlink"),
        ):
            # Run capture_pane and kill_window concurrently
            await asyncio.gather(
                backend.capture_pane("tab1"),
                backend.kill_window("tab2"),
            )

        # Due to lock serialization, operations should not interleave:
        # Either [go-to, dump-screen, go-to, close-tab]
        # or [go-to, close-tab, go-to, dump-screen]
        # but never [go-to, go-to, ...]
        assert len(order) == 4
        # First two should be from one operation, last two from another
        assert order[0] == "go-to-tab-name"
        assert order[2] == "go-to-tab-name"
