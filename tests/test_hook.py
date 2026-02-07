"""Tests for ccbot.hook — hook install detection and session map writing."""

import json
import re
from pathlib import Path

from ccbot.hook import _UUID_RE, _find_ccbot_path, _is_hook_installed
from ccbot.utils import atomic_write_json


# ── Hook install detection ───────────────────────────────────────────────


class TestIsHookInstalled:
    def test_exact_match(self):
        settings = {
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": "ccbot hook", "timeout": 5}]}
                ]
            }
        }
        assert _is_hook_installed(settings) is True

    def test_full_path_match(self):
        settings = {
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": "/usr/local/bin/ccbot hook"}]}
                ]
            }
        }
        assert _is_hook_installed(settings) is True

    def test_empty_settings(self):
        assert _is_hook_installed({}) is False

    def test_different_command(self):
        settings = {
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": "other-tool hook"}]}
                ]
            }
        }
        assert _is_hook_installed(settings) is False

    def test_no_session_start_key(self):
        settings = {"hooks": {"OtherHook": []}}
        assert _is_hook_installed(settings) is False


# ── Session map writing ──────────────────────────────────────────────────


class TestSessionMapWriting:
    def test_write_new_entry(self, tmp_path: Path):
        map_file = tmp_path / "session_map.json"
        data = {"ccbot:proj1": {"session_id": "sid-1", "cwd": "/home/proj1"}}
        atomic_write_json(map_file, data)
        result = json.loads(map_file.read_text())
        assert result["ccbot:proj1"]["session_id"] == "sid-1"

    def test_merge_with_existing(self, tmp_path: Path):
        map_file = tmp_path / "session_map.json"
        initial = {"ccbot:proj1": {"session_id": "sid-1", "cwd": "/p1"}}
        atomic_write_json(map_file, initial)

        # Read, merge, write
        existing = json.loads(map_file.read_text())
        existing["ccbot:proj2"] = {"session_id": "sid-2", "cwd": "/p2"}
        atomic_write_json(map_file, existing)

        result = json.loads(map_file.read_text())
        assert "ccbot:proj1" in result
        assert "ccbot:proj2" in result

    def test_overwrite_same_key(self, tmp_path: Path):
        map_file = tmp_path / "session_map.json"
        data = {"ccbot:proj1": {"session_id": "old-sid", "cwd": "/p"}}
        atomic_write_json(map_file, data)

        data["ccbot:proj1"] = {"session_id": "new-sid", "cwd": "/p"}
        atomic_write_json(map_file, data)

        result = json.loads(map_file.read_text())
        assert result["ccbot:proj1"]["session_id"] == "new-sid"


# ── UUID validation ──────────────────────────────────────────────────────


class TestUuidValidation:
    def test_valid_uuid(self):
        assert _UUID_RE.match("12345678-1234-1234-1234-123456789abc") is not None

    def test_invalid_uuid_too_short(self):
        assert _UUID_RE.match("1234-5678") is None

    def test_invalid_uuid_uppercase(self):
        assert _UUID_RE.match("12345678-1234-1234-1234-123456789ABC") is None

    def test_invalid_uuid_no_dashes(self):
        assert _UUID_RE.match("123456781234123412341234567890ab") is None


# ── _find_ccbot_path ─────────────────────────────────────────────────────


class TestFindCcbotPath:
    def test_returns_string(self):
        result = _find_ccbot_path()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_fallback_returns_ccbot(self):
        # Even if not found, should return "ccbot" as fallback
        result = _find_ccbot_path()
        assert "ccbot" in result
