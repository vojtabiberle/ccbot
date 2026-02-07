"""Tests for ccbot.session async resolution methods."""

import json
from pathlib import Path

import pytest

from ccbot.session import SessionManager


@pytest.fixture
def session_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Set up a SessionManager with temp files for async session resolution tests."""
    state_file = tmp_path / "state.json"
    projects_path = tmp_path / "projects"
    session_map_file = tmp_path / "session_map.json"

    from ccbot import config as config_mod
    monkeypatch.setattr(config_mod.config, "state_file", state_file)
    monkeypatch.setattr(config_mod.config, "session_map_file", session_map_file)
    monkeypatch.setattr(config_mod.config, "claude_projects_path", projects_path)

    return {
        "tmp_path": tmp_path,
        "state_file": state_file,
        "projects_path": projects_path,
        "session_map_file": session_map_file,
    }


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e) for e in entries]
    path.write_text("\n".join(lines) + "\n")


class TestGetSessionDirect:
    @pytest.mark.asyncio
    async def test_real_jsonl_returns_session(self, session_env: dict):
        cwd = "/tmp/myproject"
        sid = "test-session-id"
        encoded = cwd.replace("/", "-")
        jsonl_path = session_env["projects_path"] / encoded / f"{sid}.jsonl"
        _write_jsonl(jsonl_path, [
            {"type": "user", "message": {"content": [{"type": "text", "text": "hello"}]}, "cwd": cwd},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}},
        ])

        mgr = SessionManager()
        result = await mgr._get_session_direct(sid, cwd)
        assert result is not None
        assert result.session_id == sid

    @pytest.mark.asyncio
    async def test_summary_from_user_message(self, session_env: dict):
        cwd = "/tmp/proj"
        sid = "sid-1"
        encoded = cwd.replace("/", "-")
        jsonl_path = session_env["projects_path"] / encoded / f"{sid}.jsonl"
        _write_jsonl(jsonl_path, [
            {"type": "user", "message": {"content": [{"type": "text", "text": "Fix the login bug"}]}, "cwd": cwd},
        ])

        mgr = SessionManager()
        result = await mgr._get_session_direct(sid, cwd)
        assert result is not None
        assert "Fix the login bug" in result.summary

    @pytest.mark.asyncio
    async def test_file_not_found_returns_none(self, session_env: dict):
        mgr = SessionManager()
        result = await mgr._get_session_direct("no-such-sid", "/no/such/path")
        assert result is None

    @pytest.mark.asyncio
    async def test_glob_fallback(self, session_env: dict):
        """If direct path doesn't exist, should try glob fallback."""
        sid = "glob-sid"
        # Put file in a differently encoded dir (simulates path mismatch)
        alt_dir = session_env["projects_path"] / "-other-dir"
        alt_dir.mkdir(parents=True)
        jsonl_path = alt_dir / f"{sid}.jsonl"
        _write_jsonl(jsonl_path, [
            {"type": "user", "message": {"content": [{"type": "text", "text": "test"}]}, "cwd": "/other/dir"},
        ])

        mgr = SessionManager()
        # Use wrong cwd so direct path doesn't match, but glob should find it
        result = await mgr._get_session_direct(sid, "/wrong/cwd")
        assert result is not None
        assert result.session_id == sid


class TestGetRecentMessages:
    @pytest.mark.asyncio
    async def test_full_read(self, session_env: dict):
        cwd = "/tmp/proj"
        sid = "sid-msg"
        encoded = cwd.replace("/", "-")
        jsonl_path = session_env["projects_path"] / encoded / f"{sid}.jsonl"
        _write_jsonl(jsonl_path, [
            {"type": "user", "message": {"content": [{"type": "text", "text": "hello"}]}, "cwd": cwd},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "world"}]}},
        ])

        session_map = {f"ccbot:{sid}": {"session_id": sid, "cwd": cwd}}
        session_env["session_map_file"].write_text(json.dumps(session_map))

        mgr = SessionManager()
        await mgr.load_session_map()
        # Manually set window state
        ws = mgr.get_window_state(sid)
        ws.session_id = sid
        ws.cwd = cwd

        messages, count = await mgr.get_recent_messages(sid)
        assert count >= 1

    @pytest.mark.asyncio
    async def test_no_session_returns_empty(self, session_env: dict):
        mgr = SessionManager()
        messages, count = await mgr.get_recent_messages("nonexistent")
        assert messages == []
        assert count == 0

    @pytest.mark.asyncio
    async def test_missing_file_returns_empty(self, session_env: dict):
        mgr = SessionManager()
        ws = mgr.get_window_state("win1")
        ws.session_id = "sid"
        ws.cwd = "/tmp/no"
        messages, count = await mgr.get_recent_messages("win1")
        assert messages == []
        assert count == 0
