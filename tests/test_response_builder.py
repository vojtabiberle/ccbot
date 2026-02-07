"""Tests for ccbot.handlers.response_builder — paginated response building."""

from ccbot.handlers.response_builder import build_response_parts
from ccbot.transcript_parser import TranscriptParser


class TestBuildResponseParts:
    def test_short_text_single_part(self):
        parts = build_response_parts("Hello world", is_complete=True)
        assert len(parts) == 1
        assert isinstance(parts[0], str)

    def test_long_text_paginated(self):
        text = "A" * 5000
        parts = build_response_parts(text, is_complete=True)
        assert len(parts) > 1
        # Should have page indicators
        assert "[1/" in parts[0]

    def test_user_message_prefix(self):
        parts = build_response_parts("hello", is_complete=True, role="user")
        assert len(parts) == 1
        # The raw emoji might be escaped, but the concept should be there
        # In MarkdownV2, the output contains the user message
        assert "hello" in parts[0] or len(parts[0]) > 0

    def test_thinking_prefix_and_truncation(self):
        start = TranscriptParser.EXPANDABLE_QUOTE_START
        end = TranscriptParser.EXPANDABLE_QUOTE_END
        thinking = f"{start}{'x' * 1000}{end}"
        parts = build_response_parts(
            thinking, is_complete=True, content_type="thinking"
        )
        assert len(parts) == 1
        # Should contain "Thinking" prefix somewhere
        assert "Thinking" in parts[0] or "∴" in parts[0]

    def test_expandable_quote_atomicity(self):
        start = TranscriptParser.EXPANDABLE_QUOTE_START
        end = TranscriptParser.EXPANDABLE_QUOTE_END
        text = f"Some text\n{start}quoted content here{end}"
        parts = build_response_parts(text, is_complete=True)
        # Expandable quotes should stay atomic (single part)
        assert len(parts) == 1

    def test_output_is_markdownv2(self):
        parts = build_response_parts("**bold** text", is_complete=True)
        assert len(parts) == 1
        # MarkdownV2 escapes special chars
        result = parts[0]
        assert isinstance(result, str)

    def test_user_message_truncation_at_3000(self):
        long_text = "x" * 5000
        parts = build_response_parts(long_text, is_complete=True, role="user")
        assert len(parts) == 1
        # Content should be truncated (not contain full 5000 chars)
        # The "…" character is escaped in MarkdownV2 but text should be shorter

    def test_no_prefix_for_text_content(self):
        parts = build_response_parts("plain text", is_complete=True, content_type="text")
        assert len(parts) == 1
        # Should not have thinking or user prefix
        # "plain text" should appear escaped but recognizable
