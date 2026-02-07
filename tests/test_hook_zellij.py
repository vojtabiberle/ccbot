"""Tests for Zellij hook detection and KDL parsing in ccbot.hook."""

from unittest.mock import MagicMock, patch

from ccbot.hook import (
    _detect_multiplexer,
    _get_tmux_session_window_key,
    _get_zellij_session_window_key,
)


# ── _detect_multiplexer ─────────────────────────────────────────────────


class TestDetectMultiplexer:
    def test_tmux_detected(self, monkeypatch):
        monkeypatch.setenv("TMUX_PANE", "%5")
        monkeypatch.delenv("ZELLIJ", raising=False)
        assert _detect_multiplexer() == "tmux"

    def test_zellij_detected(self, monkeypatch):
        monkeypatch.delenv("TMUX_PANE", raising=False)
        monkeypatch.setenv("ZELLIJ", "0.42.0")
        assert _detect_multiplexer() == "zellij"

    def test_tmux_takes_priority(self, monkeypatch):
        """When both are set, TMUX_PANE wins (checked first)."""
        monkeypatch.setenv("TMUX_PANE", "%5")
        monkeypatch.setenv("ZELLIJ", "0.42.0")
        assert _detect_multiplexer() == "tmux"

    def test_neither_detected(self, monkeypatch):
        monkeypatch.delenv("TMUX_PANE", raising=False)
        monkeypatch.delenv("ZELLIJ", raising=False)
        assert _detect_multiplexer() == "unknown"


# ── _get_tmux_session_window_key ─────────────────────────────────────────


class TestGetTmuxKey:
    def test_success(self, monkeypatch):
        monkeypatch.setenv("TMUX_PANE", "%5")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="ccbot:myproject\n")
            result = _get_tmux_session_window_key()
        assert result == "ccbot:myproject"

    def test_no_pane(self, monkeypatch):
        monkeypatch.delenv("TMUX_PANE", raising=False)
        result = _get_tmux_session_window_key()
        assert result is None

    def test_bad_output(self, monkeypatch):
        monkeypatch.setenv("TMUX_PANE", "%5")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="badformat\n")
            result = _get_tmux_session_window_key()
        assert result is None


# ── _get_zellij_session_window_key ───────────────────────────────────────


# Sample KDL layouts for testing
KDL_LAYOUT_NAME_BEFORE_FOCUS = """\
layout {
    tab name="proj-a" {
        pane cwd="/home/user/proj-a"
    }
    tab name="proj-b" focus=true {
        pane cwd="/home/user/proj-b"
    }
    tab name="proj-c" {
        pane cwd="/home/user/proj-c"
    }
}
"""

KDL_LAYOUT_FOCUS_BEFORE_NAME = """\
layout {
    tab focus=true name="my-tab" {
        pane cwd="/home/user/my-tab"
    }
}
"""

KDL_LAYOUT_NO_FOCUS = """\
layout {
    tab name="tab1" {
        pane cwd="/tmp"
    }
    tab name="tab2" {
        pane cwd="/tmp"
    }
}
"""

KDL_LAYOUT_MULTIPLE_ATTRS = """\
layout {
    tab split_direction="horizontal" name="editor" size="50%" focus=true {
        pane cwd="/workspace"
    }
}
"""


class TestGetZellijKey:
    def test_name_before_focus(self, monkeypatch):
        monkeypatch.setenv("ZELLIJ_SESSION_NAME", "ccbot")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=KDL_LAYOUT_NAME_BEFORE_FOCUS, returncode=0,
            )
            result = _get_zellij_session_window_key()
        assert result == "ccbot:proj-b"

    def test_focus_before_name(self, monkeypatch):
        monkeypatch.setenv("ZELLIJ_SESSION_NAME", "ccbot")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=KDL_LAYOUT_FOCUS_BEFORE_NAME, returncode=0,
            )
            result = _get_zellij_session_window_key()
        assert result == "ccbot:my-tab"

    def test_no_focused_tab(self, monkeypatch):
        monkeypatch.setenv("ZELLIJ_SESSION_NAME", "ccbot")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=KDL_LAYOUT_NO_FOCUS, returncode=0,
            )
            result = _get_zellij_session_window_key()
        assert result is None

    def test_multiple_attrs(self, monkeypatch):
        """Tab line with extra attributes before name/focus still works."""
        monkeypatch.setenv("ZELLIJ_SESSION_NAME", "ccbot")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=KDL_LAYOUT_MULTIPLE_ATTRS, returncode=0,
            )
            result = _get_zellij_session_window_key()
        assert result == "ccbot:editor"

    def test_no_session_name(self, monkeypatch):
        monkeypatch.delenv("ZELLIJ_SESSION_NAME", raising=False)
        result = _get_zellij_session_window_key()
        assert result is None

    def test_dump_layout_fails(self, monkeypatch):
        monkeypatch.setenv("ZELLIJ_SESSION_NAME", "ccbot")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="", returncode=1, stderr="error",
            )
            result = _get_zellij_session_window_key()
        assert result is None
