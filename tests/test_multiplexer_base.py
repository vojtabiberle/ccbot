"""Tests for multiplexer abstraction — ABC, MuxWindow, factory, find_window_by_name."""

import asyncio

import pytest

from ccbot.multiplexer.base import MultiplexerBackend, MuxWindow


# ── MuxWindow dataclass ─────────────────────────────────────────────────


class TestMuxWindow:
    def test_creation(self):
        w = MuxWindow(window_id="@5", window_name="proj", cwd="/tmp/proj")
        assert w.window_id == "@5"
        assert w.window_name == "proj"
        assert w.cwd == "/tmp/proj"

    def test_equality(self):
        w1 = MuxWindow(window_id="@5", window_name="proj", cwd="/tmp")
        w2 = MuxWindow(window_id="@5", window_name="proj", cwd="/tmp")
        assert w1 == w2

    def test_inequality(self):
        w1 = MuxWindow(window_id="@5", window_name="proj", cwd="/tmp")
        w2 = MuxWindow(window_id="@6", window_name="proj", cwd="/tmp")
        assert w1 != w2


# ── Concrete stub for testing ABC defaults ───────────────────────────────


class StubBackend(MultiplexerBackend):
    """Minimal concrete backend for testing base class methods."""

    def __init__(self, windows: list[MuxWindow] | None = None) -> None:
        super().__init__("test-session", "__main__")
        self._windows = windows or []

    def get_or_create_session(self) -> None:
        pass

    async def list_windows(self) -> list[MuxWindow]:
        return list(self._windows)

    async def capture_pane(self, window_id: str, with_ansi: bool = False) -> str | None:
        return None

    async def send_keys(
        self, window_id: str, text: str, enter: bool = True, literal: bool = True,
    ) -> bool:
        return True

    async def kill_window(self, window_id: str) -> bool:
        return True

    async def create_window(
        self, work_dir: str, window_name: str | None = None, start_claude: bool = True,
    ) -> tuple[bool, str, str]:
        return True, "ok", window_name or "test"


# ── find_window_by_name (default impl) ──────────────────────────────────


class TestFindWindowByName:
    @pytest.fixture
    def backend(self) -> StubBackend:
        return StubBackend(windows=[
            MuxWindow(window_id="@1", window_name="proj-a", cwd="/a"),
            MuxWindow(window_id="@2", window_name="proj-b", cwd="/b"),
            MuxWindow(window_id="@3", window_name="proj-c", cwd="/c"),
        ])

    @pytest.mark.asyncio
    async def test_found(self, backend: StubBackend):
        w = await backend.find_window_by_name("proj-b")
        assert w is not None
        assert w.window_id == "@2"
        assert w.window_name == "proj-b"

    @pytest.mark.asyncio
    async def test_not_found(self, backend: StubBackend):
        w = await backend.find_window_by_name("nonexistent")
        assert w is None

    @pytest.mark.asyncio
    async def test_empty_list(self):
        backend = StubBackend(windows=[])
        w = await backend.find_window_by_name("anything")
        assert w is None


# ── Factory get_mux() ───────────────────────────────────────────────────


class TestGetMux:
    def test_returns_tmux_backend_by_default(self, monkeypatch):
        """Default config (MULTIPLEXER=tmux) returns TmuxBackend."""
        import ccbot.multiplexer as mux_pkg
        from ccbot.multiplexer.tmux_backend import TmuxBackend

        # Reset singleton
        monkeypatch.setattr(mux_pkg, "_mux", None)
        monkeypatch.setattr("ccbot.config.config.multiplexer_backend", "tmux")
        monkeypatch.setattr("ccbot.config.config.mux_session_name", "test-session")
        monkeypatch.setattr("ccbot.config.config.mux_main_window_name", "__main__")

        result = mux_pkg.get_mux()
        assert isinstance(result, TmuxBackend)

    def test_returns_zellij_backend(self, monkeypatch):
        """MULTIPLEXER=zellij returns ZellijBackend."""
        import ccbot.multiplexer as mux_pkg
        from ccbot.multiplexer.zellij_backend import ZellijBackend

        monkeypatch.setattr(mux_pkg, "_mux", None)
        monkeypatch.setattr("ccbot.config.config.multiplexer_backend", "zellij")
        monkeypatch.setattr("ccbot.config.config.mux_session_name", "test-session")
        monkeypatch.setattr("ccbot.config.config.mux_main_window_name", "__main__")

        result = mux_pkg.get_mux()
        assert isinstance(result, ZellijBackend)

    def test_singleton_returns_same_instance(self, monkeypatch):
        """Calling get_mux() twice returns the same instance."""
        import ccbot.multiplexer as mux_pkg
        from ccbot.multiplexer.tmux_backend import TmuxBackend

        monkeypatch.setattr(mux_pkg, "_mux", None)
        monkeypatch.setattr("ccbot.config.config.multiplexer_backend", "tmux")
        monkeypatch.setattr("ccbot.config.config.mux_session_name", "test-session")
        monkeypatch.setattr("ccbot.config.config.mux_main_window_name", "__main__")

        first = mux_pkg.get_mux()
        second = mux_pkg.get_mux()
        assert first is second

    def test_invalid_backend_raises(self, monkeypatch):
        """Unknown MULTIPLEXER value raises ValueError."""
        import ccbot.multiplexer as mux_pkg

        monkeypatch.setattr(mux_pkg, "_mux", None)
        monkeypatch.setattr("ccbot.config.config.multiplexer_backend", "invalid")

        with pytest.raises(ValueError, match="Unknown multiplexer backend"):
            mux_pkg.get_mux()
