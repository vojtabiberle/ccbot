"""Shared test fixtures and helpers for ccbot test suite.

Sets config env vars before any ccbot import, provides JSONL builders
and sample data fixtures for transcript/terminal parser tests.
"""

import json
import os

# Config isolation: set required env vars BEFORE any ccbot module import.
# config.py creates a singleton at import time requiring these.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-000")
os.environ.setdefault("ALLOWED_USERS", "12345")

from pathlib import Path
from typing import Any

import pytest


# ── JSONL builder helpers ────────────────────────────────────────────────


def make_user_text(text: str, timestamp: str = "2025-01-01T00:00:00Z") -> dict[str, Any]:
    """Build a user text JSONL entry."""
    return {
        "type": "user",
        "message": {"content": [{"type": "text", "text": text}]},
        "timestamp": timestamp,
    }


def make_assistant_text(text: str, timestamp: str = "2025-01-01T00:00:01Z") -> dict[str, Any]:
    """Build an assistant text JSONL entry."""
    return {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": text}]},
        "timestamp": timestamp,
    }


def make_tool_use(
    tool_id: str,
    name: str,
    input_data: dict[str, Any] | None = None,
    timestamp: str = "2025-01-01T00:00:02Z",
) -> dict[str, Any]:
    """Build an assistant message with a tool_use block."""
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": name,
                    "input": input_data or {},
                }
            ]
        },
        "timestamp": timestamp,
    }


def make_tool_result(
    tool_use_id: str,
    text: str = "",
    is_error: bool = False,
    timestamp: str = "2025-01-01T00:00:03Z",
) -> dict[str, Any]:
    """Build a user message with a tool_result block."""
    return {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": text,
                    "is_error": is_error,
                }
            ]
        },
        "timestamp": timestamp,
    }


def make_thinking(
    thinking_text: str, timestamp: str = "2025-01-01T00:00:04Z"
) -> dict[str, Any]:
    """Build an assistant message with a thinking block."""
    return {
        "type": "assistant",
        "message": {"content": [{"type": "thinking", "thinking": thinking_text}]},
        "timestamp": timestamp,
    }


@pytest.fixture
def sample_jsonl_file(tmp_path: Path):
    """Factory fixture: create a JSONL file from a list of dicts."""

    def _create(entries: list[dict[str, Any]], filename: str = "test.jsonl") -> Path:
        p = tmp_path / filename
        lines = [json.dumps(e) for e in entries]
        p.write_text("\n".join(lines) + "\n")
        return p

    return _create


# ── Realistic pane capture constants ─────────────────────────────────────

PANE_ASK_USER_QUESTION = """\
  ☐ Option A
  ☐ Option B
  ☐ Option C (Recommended)

  Enter to select, arrows to navigate
"""

PANE_EXIT_PLAN_MODE = """\
  Would you like to proceed?

  Some plan description here
  with multiple lines

  ctrl-g to edit in editor
"""

PANE_EXIT_PLAN_MODE_V2 = """\
  Claude has written up a plan for this task

  1. Step one
  2. Step two

  Esc to cancel
"""

PANE_PERMISSION_PROMPT = """\
  Do you want to proceed?

  Allow running: rm -rf temp/

  Esc to cancel
"""

PANE_PERMISSION_PROMPT_V2 = """\
──────────────────── Edit file ────────────────────
  Do you want to make this edit to src/config.py?

  ❯ 1. Yes
    2. Yes, allow all edits in project/ during this session (shift+tab)
    3. No

  Enter confirm · Esc cancel
───────────────────────────────────────────────────
"""

PANE_PERMISSION_PROMPT_BASH = """\
Some previous output

──────────────────────────────── Bash command ────────────────────────────────────

   docker compose up -d
   Start WordPress and MariaDB containers

 Do you want to proceed?
 ❯ 1. Yes
   2. Yes, and don't ask again for docker compose commands in /home/user/project
   3. No

 Esc to cancel · Tab to amend · ctrl+e to explain
"""

PANE_RESTORE_CHECKPOINT = """\
  Restore the code to this checkpoint?

  Files changed: 3
  Lines changed: +42 / -18

  Enter to continue
"""

PANE_PLAIN_TEXT = """\
Hello, this is just a normal terminal output.
Nothing interactive here.
"""

PANE_STATUS_DOT = """\
Some output above

· Reading files...
"""

PANE_STATUS_STAR = """\
Previous content

✻ Working on task...
"""
