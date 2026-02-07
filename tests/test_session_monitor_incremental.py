"""Tests for ccbot.session_monitor — incremental reading and mtime cache."""

import json
from pathlib import Path

import pytest

from ccbot.monitor_state import TrackedSession
from ccbot.session_monitor import SessionMonitor


@pytest.fixture
def monitor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SessionMonitor:
    """Create a SessionMonitor with temp paths."""
    from ccbot import config as config_mod
    monkeypatch.setattr(config_mod.config, "claude_projects_path", tmp_path / "projects")
    monkeypatch.setattr(config_mod.config, "monitor_state_file", tmp_path / "mstate.json")
    monkeypatch.setattr(config_mod.config, "session_map_file", tmp_path / "smap.json")

    return SessionMonitor(
        projects_path=tmp_path / "projects",
        poll_interval=1.0,
        state_file=tmp_path / "mstate.json",
    )


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e) for e in entries]
    path.write_text("\n".join(lines) + "\n")


class TestReadNewLines:
    @pytest.mark.asyncio
    async def test_read_from_offset_zero(self, monitor: SessionMonitor, tmp_path: Path):
        fpath = tmp_path / "test.jsonl"
        _write_jsonl(fpath, [
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "hello"}]}},
        ])
        session = TrackedSession("sid1", str(fpath), last_byte_offset=0)
        entries = await monitor._read_new_lines(session, fpath)
        assert len(entries) == 1
        assert session.last_byte_offset > 0

    @pytest.mark.asyncio
    async def test_incremental_read_after_append(self, monitor: SessionMonitor, tmp_path: Path):
        fpath = tmp_path / "test.jsonl"
        _write_jsonl(fpath, [
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "first"}]}},
        ])
        session = TrackedSession("sid1", str(fpath), last_byte_offset=0)

        # First read
        entries1 = await monitor._read_new_lines(session, fpath)
        assert len(entries1) == 1
        old_offset = session.last_byte_offset

        # Append more data
        with open(fpath, "a") as f:
            f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "second"}]}}) + "\n")

        # Incremental read
        entries2 = await monitor._read_new_lines(session, fpath)
        assert len(entries2) == 1
        assert session.last_byte_offset > old_offset

    @pytest.mark.asyncio
    async def test_truncation_detection_reset(self, monitor: SessionMonitor, tmp_path: Path):
        fpath = tmp_path / "test.jsonl"
        _write_jsonl(fpath, [
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "a"}]}},
        ])
        # Set offset beyond file size (simulates truncation)
        session = TrackedSession("sid1", str(fpath), last_byte_offset=999999)
        entries = await monitor._read_new_lines(session, fpath)
        # Should reset and read from start
        assert len(entries) >= 1
        assert session.last_byte_offset < 999999

    @pytest.mark.asyncio
    async def test_empty_file(self, monitor: SessionMonitor, tmp_path: Path):
        fpath = tmp_path / "empty.jsonl"
        fpath.write_text("")
        session = TrackedSession("sid1", str(fpath), last_byte_offset=0)
        entries = await monitor._read_new_lines(session, fpath)
        assert len(entries) == 0

    @pytest.mark.asyncio
    async def test_invalid_json_lines_skipped(self, monitor: SessionMonitor, tmp_path: Path):
        fpath = tmp_path / "test.jsonl"
        fpath.write_text(
            "not valid json\n"
            + json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "valid"}]}}) + "\n"
            + "also bad{}\n"
        )
        session = TrackedSession("sid1", str(fpath), last_byte_offset=0)
        entries = await monitor._read_new_lines(session, fpath)
        assert len(entries) == 1


class TestMtimeCache:
    def test_mtime_tracking(self, monitor: SessionMonitor):
        """Mtime cache starts empty and can be set."""
        assert len(monitor._file_mtimes) == 0
        monitor._file_mtimes["sid1"] = 12345.0
        assert monitor._file_mtimes["sid1"] == 12345.0

    def test_cache_reset_on_new_session(self, monitor: SessionMonitor):
        """Removing mtime entry simulates cache reset."""
        monitor._file_mtimes["sid1"] = 1.0
        monitor._file_mtimes.pop("sid1", None)
        assert "sid1" not in monitor._file_mtimes
