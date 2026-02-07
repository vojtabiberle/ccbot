"""Tests for ccbot.monitor_state — byte offset persistence."""

import json
from pathlib import Path

from ccbot.monitor_state import MonitorState, TrackedSession


class TestTrackedSession:
    def test_to_dict_from_dict_roundtrip(self):
        ts = TrackedSession(
            session_id="abc-123",
            file_path="/tmp/test.jsonl",
            last_byte_offset=500,
        )
        d = ts.to_dict()
        restored = TrackedSession.from_dict(d)
        assert restored.session_id == ts.session_id
        assert restored.file_path == ts.file_path
        assert restored.last_byte_offset == ts.last_byte_offset

    def test_defaults_for_missing_keys(self):
        ts = TrackedSession.from_dict({})
        assert ts.session_id == ""
        assert ts.file_path == ""
        assert ts.last_byte_offset == 0


class TestMonitorStateCrud:
    def test_empty_state(self, tmp_path: Path):
        state = MonitorState(state_file=tmp_path / "state.json")
        assert len(state.tracked_sessions) == 0

    def test_update_and_get(self, tmp_path: Path):
        state = MonitorState(state_file=tmp_path / "state.json")
        ts = TrackedSession("sid1", "/path.jsonl", 100)
        state.update_session(ts)
        result = state.get_session("sid1")
        assert result is not None
        assert result.session_id == "sid1"
        assert result.last_byte_offset == 100

    def test_remove(self, tmp_path: Path):
        state = MonitorState(state_file=tmp_path / "state.json")
        ts = TrackedSession("sid1", "/path.jsonl")
        state.update_session(ts)
        state.remove_session("sid1")
        assert state.get_session("sid1") is None

    def test_remove_nonexistent(self, tmp_path: Path):
        state = MonitorState(state_file=tmp_path / "state.json")
        # Should not raise
        state.remove_session("does-not-exist")

    def test_dirty_flag_on_update(self, tmp_path: Path):
        state = MonitorState(state_file=tmp_path / "state.json")
        assert state._dirty is False
        ts = TrackedSession("sid1", "/path.jsonl")
        state.update_session(ts)
        assert state._dirty is True

    def test_dirty_cleared_on_save(self, tmp_path: Path):
        state = MonitorState(state_file=tmp_path / "state.json")
        ts = TrackedSession("sid1", "/path.jsonl")
        state.update_session(ts)
        assert state._dirty is True
        state.save()
        assert state._dirty is False


class TestMonitorStatePersistence:
    def test_save_load_roundtrip(self, tmp_path: Path):
        state_file = tmp_path / "state.json"
        state = MonitorState(state_file=state_file)
        ts = TrackedSession("sid1", "/path.jsonl", 42)
        state.update_session(ts)
        state.save()

        state2 = MonitorState(state_file=state_file)
        state2.load()
        result = state2.get_session("sid1")
        assert result is not None
        assert result.last_byte_offset == 42

    def test_load_nonexistent_file(self, tmp_path: Path):
        state = MonitorState(state_file=tmp_path / "missing.json")
        state.load()  # Should not raise
        assert len(state.tracked_sessions) == 0

    def test_load_corrupted_json(self, tmp_path: Path):
        state_file = tmp_path / "bad.json"
        state_file.write_text("not valid json{{{")
        state = MonitorState(state_file=state_file)
        state.load()  # Should not raise
        assert len(state.tracked_sessions) == 0

    def test_save_if_dirty_skips_when_clean(self, tmp_path: Path):
        state_file = tmp_path / "state.json"
        state = MonitorState(state_file=state_file)
        state.save_if_dirty()
        # File should not be created since nothing is dirty
        assert not state_file.exists()

    def test_creates_parent_dirs(self, tmp_path: Path):
        state_file = tmp_path / "sub" / "dir" / "state.json"
        state = MonitorState(state_file=state_file)
        ts = TrackedSession("sid1", "/path.jsonl")
        state.update_session(ts)
        state.save()
        assert state_file.exists()
