"""Tests for ccbot.transcript_parser — JSONL parsing and tool pairing."""

import json

from ccbot.transcript_parser import (
    ParsedEntry,
    PendingToolInfo,
    TranscriptParser,
)

from conftest import (
    make_assistant_text,
    make_thinking,
    make_tool_result,
    make_tool_use,
    make_user_text,
)


# ── parse_line ───────────────────────────────────────────────────────────


class TestParseLine:
    def test_valid_json(self):
        result = TranscriptParser.parse_line('{"type": "user"}')
        assert result == {"type": "user"}

    def test_empty_string(self):
        assert TranscriptParser.parse_line("") is None

    def test_whitespace_only(self):
        assert TranscriptParser.parse_line("   \t  ") is None

    def test_invalid_json(self):
        assert TranscriptParser.parse_line("not json{") is None

    def test_strips_whitespace(self):
        result = TranscriptParser.parse_line('  {"key": "val"}  ')
        assert result == {"key": "val"}


# ── extract_text_only ────────────────────────────────────────────────────


class TestExtractTextOnly:
    def test_text_blocks_list(self):
        content = [
            {"type": "text", "text": "hello"},
            {"type": "text", "text": "world"},
        ]
        assert TranscriptParser.extract_text_only(content) == "hello\nworld"

    def test_skip_tool_use(self):
        content = [
            {"type": "text", "text": "before"},
            {"type": "tool_use", "id": "x", "name": "Read"},
            {"type": "text", "text": "after"},
        ]
        assert TranscriptParser.extract_text_only(content) == "before\nafter"

    def test_string_input(self):
        assert TranscriptParser.extract_text_only("just a string") == "just a string"  # type: ignore[arg-type]

    def test_empty_list(self):
        assert TranscriptParser.extract_text_only([]) == ""

    def test_non_list_non_string(self):
        assert TranscriptParser.extract_text_only(42) == ""  # type: ignore[arg-type]


# ── format_tool_use_summary ──────────────────────────────────────────────


class TestFormatToolUseSummary:
    def test_read_tool(self):
        result = TranscriptParser.format_tool_use_summary("Read", {"file_path": "/a/b.py"})
        assert result == "**Read**(/a/b.py)"

    def test_write_tool(self):
        result = TranscriptParser.format_tool_use_summary("Write", {"file_path": "/out.txt"})
        assert result == "**Write**(/out.txt)"

    def test_bash_tool(self):
        result = TranscriptParser.format_tool_use_summary("Bash", {"command": "ls -la"})
        assert result == "**Bash**(ls -la)"

    def test_grep_tool(self):
        result = TranscriptParser.format_tool_use_summary("Grep", {"pattern": "TODO"})
        assert result == "**Grep**(TODO)"

    def test_glob_tool(self):
        result = TranscriptParser.format_tool_use_summary("Glob", {"pattern": "*.py"})
        assert result == "**Glob**(*.py)"

    def test_webfetch_tool(self):
        result = TranscriptParser.format_tool_use_summary("WebFetch", {"url": "https://example.com"})
        assert result == "**WebFetch**(https://example.com)"

    def test_websearch_tool(self):
        result = TranscriptParser.format_tool_use_summary("WebSearch", {"query": "python async"})
        assert result == "**WebSearch**(python async)"

    def test_todowrite_tool(self):
        result = TranscriptParser.format_tool_use_summary("TodoWrite", {"todos": [1, 2, 3]})
        assert result == "**TodoWrite**(3 item(s))"

    def test_ask_user_question(self):
        result = TranscriptParser.format_tool_use_summary(
            "AskUserQuestion",
            {"questions": [{"question": "Which option?"}]},
        )
        assert result == "**AskUserQuestion**(Which option?)"

    def test_unknown_tool_generic(self):
        result = TranscriptParser.format_tool_use_summary("MyTool", {"foo": "bar"})
        assert result == "**MyTool**(bar)"

    def test_truncation_200_chars(self):
        long_path = "/a" * 150  # 300 chars
        result = TranscriptParser.format_tool_use_summary("Read", {"file_path": long_path})
        # Should truncate at 200 chars + "…"
        assert len(result) < 220
        assert "…" in result

    def test_non_dict_input(self):
        result = TranscriptParser.format_tool_use_summary("Read", "not a dict")
        assert result == "**Read**"


# ── extract_tool_result_text ─────────────────────────────────────────────


class TestExtractToolResultText:
    def test_string_input(self):
        assert TranscriptParser.extract_tool_result_text("hello") == "hello"

    def test_text_blocks(self):
        content = [
            {"type": "text", "text": "line1"},
            {"type": "text", "text": "line2"},
        ]
        assert TranscriptParser.extract_tool_result_text(content) == "line1\nline2"

    def test_mixed_blocks(self):
        content = [
            {"type": "text", "text": "a"},
            {"type": "image", "data": "..."},
            {"type": "text", "text": "b"},
        ]
        assert TranscriptParser.extract_tool_result_text(content) == "a\nb"

    def test_non_list(self):
        assert TranscriptParser.extract_tool_result_text(42) == ""


# ── _format_edit_diff ────────────────────────────────────────────────────


class TestFormatEditDiff:
    def test_single_line_change(self):
        result = TranscriptParser._format_edit_diff("old line", "new line")
        assert "-old line" in result
        assert "+new line" in result

    def test_multi_line(self):
        old = "line1\nline2\nline3"
        new = "line1\nmodified\nline3"
        result = TranscriptParser._format_edit_diff(old, new)
        assert "-line2" in result
        assert "+modified" in result

    def test_add_only(self):
        result = TranscriptParser._format_edit_diff("a", "a\nb")
        assert "+b" in result


# ── parse_entries — tool pairing ─────────────────────────────────────────


class TestParseEntries:
    def test_simple_assistant_text(self):
        entries = [make_assistant_text("Hello world")]
        result, pending = TranscriptParser.parse_entries(entries)
        assert len(result) == 1
        assert result[0].role == "assistant"
        assert result[0].text == "Hello world"
        assert result[0].content_type == "text"

    def test_user_text(self):
        entries = [make_user_text("How are you?")]
        result, _ = TranscriptParser.parse_entries(entries)
        assert len(result) == 1
        assert result[0].role == "user"
        assert result[0].text == "How are you?"

    def test_tool_use_result_pairing(self):
        entries = [
            make_tool_use("t1", "Read", {"file_path": "/test.py"}),
            make_tool_result("t1", "file contents here"),
        ]
        result, pending = TranscriptParser.parse_entries(entries)
        # Should have tool_use entry + tool_result entry
        tool_use_entries = [e for e in result if e.content_type == "tool_use"]
        tool_result_entries = [e for e in result if e.content_type == "tool_result"]
        assert len(tool_use_entries) == 1
        assert len(tool_result_entries) == 1
        assert tool_result_entries[0].tool_use_id == "t1"
        assert not pending

    def test_error_result(self):
        entries = [
            make_tool_use("t1", "Bash", {"command": "bad"}),
            make_tool_result("t1", "command not found", is_error=True),
        ]
        result, _ = TranscriptParser.parse_entries(entries)
        tool_results = [e for e in result if e.content_type == "tool_result"]
        assert len(tool_results) == 1
        assert "Error" in tool_results[0].text

    def test_interrupted_result(self):
        entries = [
            make_tool_use("t1", "Bash", {"command": "sleep 60"}),
            make_tool_result("t1", "[Request interrupted by user for tool use]"),
        ]
        result, _ = TranscriptParser.parse_entries(entries)
        tool_results = [e for e in result if e.content_type == "tool_result"]
        assert len(tool_results) == 1
        assert "Interrupted" in tool_results[0].text

    def test_thinking_block(self):
        entries = [make_thinking("Let me think about this...")]
        result, _ = TranscriptParser.parse_entries(entries)
        assert len(result) == 1
        assert result[0].content_type == "thinking"
        assert TranscriptParser.EXPANDABLE_QUOTE_START in result[0].text

    def test_edit_diff(self):
        entries = [
            make_tool_use("t1", "Edit", {
                "file_path": "/test.py",
                "old_string": "old code",
                "new_string": "new code",
            }),
            make_tool_result("t1", "File edited successfully"),
        ]
        result, _ = TranscriptParser.parse_entries(entries)
        tool_results = [e for e in result if e.content_type == "tool_result"]
        assert len(tool_results) == 1
        assert "Added" in tool_results[0].text or "removed" in tool_results[0].text

    def test_multiple_tools_per_message(self):
        entry = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "a.py"}},
                    {"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": "b.py"}},
                ]
            },
            "timestamp": "2025-01-01T00:00:00Z",
        }
        # Use carry-over mode (pending_tools={}) to avoid oneshot flush doubling entries
        result, pending = TranscriptParser.parse_entries([entry], pending_tools={})
        tool_uses = [e for e in result if e.content_type == "tool_use"]
        assert len(tool_uses) == 2
        assert len(pending) == 2

    def test_pending_carry_over(self):
        # First call: tool_use only (no result yet)
        entries1 = [make_tool_use("t1", "Bash", {"command": "ls"})]
        _, pending1 = TranscriptParser.parse_entries(entries1, pending_tools={})
        assert "t1" in pending1

        # Second call: tool_result arrives with carry-over
        entries2 = [make_tool_result("t1", "file1\nfile2")]
        result2, pending2 = TranscriptParser.parse_entries(entries2, pending_tools=pending1)
        tool_results = [e for e in result2 if e.content_type == "tool_result"]
        assert len(tool_results) == 1
        assert not pending2

    def test_local_command_detection(self):
        entry = {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "text",
                        "text": "<command-name>help</command-name><local-command-stdout>Usage: ...</local-command-stdout>",
                    }
                ]
            },
            "timestamp": "2025-01-01T00:00:00Z",
        }
        result, _ = TranscriptParser.parse_entries([entry])
        assert len(result) == 1
        assert result[0].content_type == "local_command"
        assert "help" in result[0].text or "Usage" in result[0].text


# ── parse_entries — tool result formatting ───────────────────────────────


class TestToolResultFormatting:
    def test_read_line_count(self):
        entries = [
            make_tool_use("t1", "Read", {"file_path": "/f.py"}),
            make_tool_result("t1", "line1\nline2\nline3"),
        ]
        result, _ = TranscriptParser.parse_entries(entries)
        tool_results = [e for e in result if e.content_type == "tool_result"]
        assert "Read 3 lines" in tool_results[0].text

    def test_write_line_count(self):
        entries = [
            make_tool_use("t1", "Write", {"file_path": "/f.py"}),
            make_tool_result("t1", "a\nb\nc\nd"),
        ]
        result, _ = TranscriptParser.parse_entries(entries)
        tool_results = [e for e in result if e.content_type == "tool_result"]
        assert "Wrote 4 lines" in tool_results[0].text

    def test_bash_output_with_quote(self):
        entries = [
            make_tool_use("t1", "Bash", {"command": "echo hi"}),
            make_tool_result("t1", "hi\nthere"),
        ]
        result, _ = TranscriptParser.parse_entries(entries)
        tool_results = [e for e in result if e.content_type == "tool_result"]
        text = tool_results[0].text
        assert "Output" in text
        assert TranscriptParser.EXPANDABLE_QUOTE_START in text

    def test_grep_matches_with_quote(self):
        entries = [
            make_tool_use("t1", "Grep", {"pattern": "TODO"}),
            make_tool_result("t1", "file1.py:10:TODO fix\nfile2.py:20:TODO clean"),
        ]
        result, _ = TranscriptParser.parse_entries(entries)
        tool_results = [e for e in result if e.content_type == "tool_result"]
        text = tool_results[0].text
        assert "Found 2 matches" in text
        assert TranscriptParser.EXPANDABLE_QUOTE_START in text

    def test_glob_files_with_quote(self):
        entries = [
            make_tool_use("t1", "Glob", {"pattern": "*.py"}),
            make_tool_result("t1", "a.py\nb.py\nc.py"),
        ]
        result, _ = TranscriptParser.parse_entries(entries)
        tool_results = [e for e in result if e.content_type == "tool_result"]
        text = tool_results[0].text
        assert "Found 3 files" in text
        assert TranscriptParser.EXPANDABLE_QUOTE_START in text

    def test_webfetch_chars_with_quote(self):
        content = "x" * 100
        entries = [
            make_tool_use("t1", "WebFetch", {"url": "https://example.com"}),
            make_tool_result("t1", content),
        ]
        result, _ = TranscriptParser.parse_entries(entries)
        tool_results = [e for e in result if e.content_type == "tool_result"]
        text = tool_results[0].text
        assert "Fetched 100 characters" in text
        assert TranscriptParser.EXPANDABLE_QUOTE_START in text


# ── parse_entries — edge cases ───────────────────────────────────────────


class TestParseEntriesEdgeCases:
    def test_skip_non_user_assistant(self):
        entries = [
            {"type": "summary", "summary": "some summary"},
            make_assistant_text("real text"),
        ]
        result, _ = TranscriptParser.parse_entries(entries)
        assert len(result) == 1
        assert result[0].text == "real text"

    def test_skip_system_xml_tags(self):
        entry = {
            "type": "user",
            "message": {
                "content": [
                    {"type": "text", "text": "<system-reminder>ignore</system-reminder>"},
                ]
            },
            "timestamp": "2025-01-01T00:00:00Z",
        }
        result, _ = TranscriptParser.parse_entries([entry])
        # system-reminder text should be filtered out
        user_texts = [e for e in result if e.role == "user" and e.content_type == "text"]
        assert len(user_texts) == 0

    def test_exit_plan_mode_plan_before_tool(self):
        entry = {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "epm1",
                        "name": "ExitPlanMode",
                        "input": {"plan": "Here is my plan:\n1. Do A\n2. Do B"},
                    }
                ]
            },
            "timestamp": "2025-01-01T00:00:00Z",
        }
        result, _ = TranscriptParser.parse_entries([entry])
        # Should have plan text BEFORE tool_use entry
        assert len(result) >= 2
        assert result[0].content_type == "text"
        assert "plan" in result[0].text.lower() or "Do A" in result[0].text

    def test_no_content_placeholder_skip(self):
        entry = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "(no content)"}]},
            "timestamp": "2025-01-01T00:00:00Z",
        }
        result, _ = TranscriptParser.parse_entries([entry])
        text_entries = [e for e in result if e.content_type == "text"]
        assert len(text_entries) == 0

    def test_pending_flush_in_oneshot_mode(self):
        # When pending_tools is None (oneshot), remaining tools should be flushed
        entries = [make_tool_use("t1", "Bash", {"command": "ls"})]
        result, pending = TranscriptParser.parse_entries(entries, pending_tools=None)
        # Should emit tool_use entries for pending tools
        tool_entries = [e for e in result if e.content_type == "tool_use"]
        assert len(tool_entries) >= 1
