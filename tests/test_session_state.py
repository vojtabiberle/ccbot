"""Tests for ccbot.session — thread bindings, window states, offsets.

Uses monkeypatch to redirect config paths to temp dirs so SessionManager
doesn't touch real state files.
"""

import json
from pathlib import Path

import pytest

from ccbot.session import SessionManager, WindowState


@pytest.fixture
def manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SessionManager:
    """Create a SessionManager with state files redirected to tmp_path."""
    state_file = tmp_path / "state.json"
    session_map_file = tmp_path / "session_map.json"
    # Patch config before constructing SessionManager
    from ccbot import config as config_mod
    monkeypatch.setattr(config_mod.config, "state_file", state_file)
    monkeypatch.setattr(config_mod.config, "session_map_file", session_map_file)
    monkeypatch.setattr(config_mod.config, "claude_projects_path", tmp_path / "projects")
    return SessionManager()


# ── Thread bindings ──────────────────────────────────────────────────────


class TestThreadBindings:
    def test_bind_and_get(self, manager: SessionManager):
        manager.bind_thread(100, 42, "myproject")
        assert manager.get_window_for_thread(100, 42) == "myproject"

    def test_unbind_returns_old_name(self, manager: SessionManager):
        manager.bind_thread(100, 42, "myproject")
        old = manager.unbind_thread(100, 42)
        assert old == "myproject"
        assert manager.get_window_for_thread(100, 42) is None

    def test_unbind_nonexistent(self, manager: SessionManager):
        assert manager.unbind_thread(100, 999) is None

    def test_reverse_lookup_get_thread_for_window(self, manager: SessionManager):
        manager.bind_thread(100, 42, "myproject")
        assert manager.get_thread_for_window(100, "myproject") == 42

    def test_get_all_thread_windows(self, manager: SessionManager):
        manager.bind_thread(100, 42, "proj1")
        manager.bind_thread(100, 43, "proj2")
        all_bindings = manager.get_all_thread_windows(100)
        assert all_bindings == {42: "proj1", 43: "proj2"}

    def test_resolve_window_for_thread_none(self, manager: SessionManager):
        assert manager.resolve_window_for_thread(100, None) is None

    def test_iter_thread_bindings(self, manager: SessionManager):
        manager.bind_thread(100, 42, "proj1")
        manager.bind_thread(200, 43, "proj2")
        items = list(manager.iter_thread_bindings())
        assert (100, 42, "proj1") in items
        assert (200, 43, "proj2") in items

    def test_persist_across_reload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        state_file = tmp_path / "state.json"
        from ccbot import config as config_mod
        monkeypatch.setattr(config_mod.config, "state_file", state_file)
        monkeypatch.setattr(config_mod.config, "session_map_file", tmp_path / "sm.json")
        monkeypatch.setattr(config_mod.config, "claude_projects_path", tmp_path / "p")

        m1 = SessionManager()
        m1.bind_thread(100, 42, "myproject")
        # Reload from same state file
        m2 = SessionManager()
        assert m2.get_window_for_thread(100, 42) == "myproject"


# ── Window states ────────────────────────────────────────────────────────


class TestWindowStates:
    def test_get_creates_new(self, manager: SessionManager):
        state = manager.get_window_state("new_window")
        assert isinstance(state, WindowState)
        assert state.session_id == ""

    def test_session_id_persists(self, manager: SessionManager):
        state = manager.get_window_state("win1")
        state.session_id = "test-sid"
        state2 = manager.get_window_state("win1")
        assert state2.session_id == "test-sid"

    def test_clear_window_session(self, manager: SessionManager):
        state = manager.get_window_state("win1")
        state.session_id = "test-sid"
        manager.clear_window_session("win1")
        assert manager.get_window_state("win1").session_id == ""

    def test_to_dict_roundtrip(self):
        ws = WindowState(session_id="sid", cwd="/tmp")
        d = ws.to_dict()
        restored = WindowState.from_dict(d)
        assert restored.session_id == "sid"
        assert restored.cwd == "/tmp"

    def test_persist_across_reload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        state_file = tmp_path / "state.json"
        from ccbot import config as config_mod
        monkeypatch.setattr(config_mod.config, "state_file", state_file)
        monkeypatch.setattr(config_mod.config, "session_map_file", tmp_path / "sm.json")
        monkeypatch.setattr(config_mod.config, "claude_projects_path", tmp_path / "p")

        m1 = SessionManager()
        ws = m1.get_window_state("win1")
        ws.session_id = "sid-123"
        ws.cwd = "/home/test"
        m1._save_state()

        m2 = SessionManager()
        ws2 = m2.get_window_state("win1")
        assert ws2.session_id == "sid-123"
        assert ws2.cwd == "/home/test"


# ── User offsets ─────────────────────────────────────────────────────────


class TestUserOffsets:
    def test_get_none_initially(self, manager: SessionManager):
        assert manager.get_user_window_offset(100, "win1") is None

    def test_update_and_get(self, manager: SessionManager):
        manager.update_user_window_offset(100, "win1", 500)
        assert manager.get_user_window_offset(100, "win1") == 500

    def test_persist_across_reload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        state_file = tmp_path / "state.json"
        from ccbot import config as config_mod
        monkeypatch.setattr(config_mod.config, "state_file", state_file)
        monkeypatch.setattr(config_mod.config, "session_map_file", tmp_path / "sm.json")
        monkeypatch.setattr(config_mod.config, "claude_projects_path", tmp_path / "p")

        m1 = SessionManager()
        m1.update_user_window_offset(100, "win1", 300)
        m2 = SessionManager()
        assert m2.get_user_window_offset(100, "win1") == 300

    def test_per_user_per_window_independence(self, manager: SessionManager):
        manager.update_user_window_offset(100, "win1", 100)
        manager.update_user_window_offset(100, "win2", 200)
        manager.update_user_window_offset(200, "win1", 300)
        assert manager.get_user_window_offset(100, "win1") == 100
        assert manager.get_user_window_offset(100, "win2") == 200
        assert manager.get_user_window_offset(200, "win1") == 300


# ── Path construction ────────────────────────────────────────────────────


class TestPathConstruction:
    def test_valid_session_id_and_cwd(self, manager: SessionManager):
        path = manager._build_session_file_path("abc-123", "/data/code/ccbot")
        assert path is not None
        assert path.name == "abc-123.jsonl"
        assert "-data-code-ccbot" in str(path)

    def test_build_session_file_path_encoded_cwd(self, manager: SessionManager):
        path = manager._build_session_file_path("sid", "/home/user/project")
        assert path is not None
        assert "-home-user-project" in str(path)

    def test_empty_inputs(self, manager: SessionManager):
        assert manager._build_session_file_path("", "/cwd") is None
        assert manager._build_session_file_path("sid", "") is None


# ── Unread detection ─────────────────────────────────────────────────────


class TestUnreadDetection:
    @pytest.mark.asyncio
    async def test_get_unread_info_with_real_jsonl(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Test unread detection with a real JSONL file."""
        state_file = tmp_path / "state.json"
        projects_path = tmp_path / "projects"
        session_map_file = tmp_path / "session_map.json"

        from ccbot import config as config_mod
        monkeypatch.setattr(config_mod.config, "state_file", state_file)
        monkeypatch.setattr(config_mod.config, "session_map_file", session_map_file)
        monkeypatch.setattr(config_mod.config, "claude_projects_path", projects_path)

        # Create a JSONL file
        encoded_dir = projects_path / "-tmp-proj"
        encoded_dir.mkdir(parents=True)
        jsonl = encoded_dir / "test-sid.jsonl"
        jsonl.write_text(
            json.dumps({"type": "user", "message": {"content": "hello"}, "cwd": "/tmp/proj"}) + "\n"
            + json.dumps({"type": "assistant", "message": {"content": "hi"}}) + "\n"
        )

        # Set up session_map
        session_map_file.write_text(json.dumps({
            "ccbot:win1": {"session_id": "test-sid", "cwd": "/tmp/proj"}
        }))

        mgr = SessionManager()
        await mgr.load_session_map()

        # No offset yet — should not be unread (initialized to file_size)
        info = await mgr.get_unread_info(100, "win1")
        assert info is not None
        assert info.has_unread is False

        # Set offset to 0 — everything is unread
        mgr.update_user_window_offset(100, "win1", 0)
        info = await mgr.get_unread_info(100, "win1")
        assert info is not None
        assert info.has_unread is True

    @pytest.mark.asyncio
    async def test_truncation_detection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Test offset > file_size (truncation) detection."""
        state_file = tmp_path / "state.json"
        projects_path = tmp_path / "projects"
        session_map_file = tmp_path / "session_map.json"

        from ccbot import config as config_mod
        monkeypatch.setattr(config_mod.config, "state_file", state_file)
        monkeypatch.setattr(config_mod.config, "session_map_file", session_map_file)
        monkeypatch.setattr(config_mod.config, "claude_projects_path", projects_path)

        encoded_dir = projects_path / "-tmp-proj"
        encoded_dir.mkdir(parents=True)
        jsonl = encoded_dir / "test-sid.jsonl"
        jsonl.write_text(json.dumps({"type": "user", "message": {"content": "x"}, "cwd": "/tmp/proj"}) + "\n")

        session_map_file.write_text(json.dumps({
            "ccbot:win1": {"session_id": "test-sid", "cwd": "/tmp/proj"}
        }))

        mgr = SessionManager()
        await mgr.load_session_map()

        # Set offset way beyond file size
        mgr.update_user_window_offset(100, "win1", 999999)
        info = await mgr.get_unread_info(100, "win1")
        assert info is not None
        # Offset > size triggers reset → has_unread should be True
        assert info.has_unread is True
