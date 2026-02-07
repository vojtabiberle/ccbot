"""Tests for ccbot.utils — atomic JSON writes and JSONL reading."""

import json
from pathlib import Path

from ccbot.utils import atomic_write_json, read_cwd_from_jsonl


class TestAtomicWriteJson:
    def test_valid_json_output(self, tmp_path: Path):
        path = tmp_path / "test.json"
        data = {"key": "value", "num": 42}
        atomic_write_json(path, data)
        result = json.loads(path.read_text())
        assert result == data

    def test_no_temp_files_left(self, tmp_path: Path):
        path = tmp_path / "test.json"
        atomic_write_json(path, {"a": 1})
        # Only the target file should exist
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].name == "test.json"

    def test_creates_parent_dirs(self, tmp_path: Path):
        path = tmp_path / "sub" / "dir" / "test.json"
        atomic_write_json(path, {"nested": True})
        assert path.exists()
        assert json.loads(path.read_text()) == {"nested": True}

    def test_roundtrip_read_back(self, tmp_path: Path):
        path = tmp_path / "roundtrip.json"
        data = {"list": [1, 2, 3], "nested": {"a": "b"}}
        atomic_write_json(path, data)
        result = json.loads(path.read_text())
        assert result == data

    def test_overwrite_existing(self, tmp_path: Path):
        path = tmp_path / "test.json"
        atomic_write_json(path, {"v": 1})
        atomic_write_json(path, {"v": 2})
        result = json.loads(path.read_text())
        assert result == {"v": 2}


class TestReadCwdFromJsonl:
    def test_reads_cwd_from_first_entry(self, tmp_path: Path):
        path = tmp_path / "test.jsonl"
        path.write_text(
            json.dumps({"type": "user", "cwd": "/home/user/project"}) + "\n"
            + json.dumps({"type": "assistant", "cwd": "/other"}) + "\n"
        )
        assert read_cwd_from_jsonl(path) == "/home/user/project"

    def test_skips_entries_without_cwd(self, tmp_path: Path):
        path = tmp_path / "test.jsonl"
        path.write_text(
            json.dumps({"type": "user"}) + "\n"
            + json.dumps({"type": "assistant", "cwd": "/found"}) + "\n"
        )
        assert read_cwd_from_jsonl(path) == "/found"

    def test_empty_file(self, tmp_path: Path):
        path = tmp_path / "empty.jsonl"
        path.write_text("")
        assert read_cwd_from_jsonl(path) == ""

    def test_nonexistent_file(self, tmp_path: Path):
        path = tmp_path / "missing.jsonl"
        assert read_cwd_from_jsonl(path) == ""
