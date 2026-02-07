"""Tests for ccbot.markdown_v2 — Markdown to MarkdownV2 conversion."""

from ccbot.markdown_v2 import _escape_mdv2, _render_expandable_quote, convert_markdown
from ccbot.transcript_parser import TranscriptParser

import re


class TestConvertMarkdown:
    def test_plain_text_escaping(self):
        result = convert_markdown("Hello world")
        # Should not crash, should produce valid MarkdownV2
        assert isinstance(result, str)
        assert len(result) > 0

    def test_bold_conversion(self):
        result = convert_markdown("**bold text**")
        # MarkdownV2 bold uses *text*
        assert "bold text" in result

    def test_code_block(self):
        result = convert_markdown("```python\nprint('hi')\n```")
        assert "print" in result

    def test_inline_code(self):
        result = convert_markdown("`code`")
        assert "code" in result

    def test_expandable_quote_rendering(self):
        start = TranscriptParser.EXPANDABLE_QUOTE_START
        end = TranscriptParser.EXPANDABLE_QUOTE_END
        text = f"before {start}quoted content{end} after"
        result = convert_markdown(text)
        # Should contain the > prefix for blockquote
        assert ">" in result
        # Should end with || for expandable
        assert "||" in result

    def test_quote_truncation_at_3800(self):
        start = TranscriptParser.EXPANDABLE_QUOTE_START
        end = TranscriptParser.EXPANDABLE_QUOTE_END
        long_text = "x" * 5000
        text = f"{start}{long_text}{end}"
        result = convert_markdown(text)
        # Result should be truncated (with room for MarkdownV2 escaping)
        assert "truncated" in result

    def test_mixed_text_and_quotes(self):
        start = TranscriptParser.EXPANDABLE_QUOTE_START
        end = TranscriptParser.EXPANDABLE_QUOTE_END
        text = f"Normal text\n{start}quoted{end}\nMore text"
        result = convert_markdown(text)
        assert isinstance(result, str)

    def test_multiple_quotes(self):
        start = TranscriptParser.EXPANDABLE_QUOTE_START
        end = TranscriptParser.EXPANDABLE_QUOTE_END
        text = f"{start}quote1{end}\n{start}quote2{end}"
        result = convert_markdown(text)
        # Both quotes rendered
        assert result.count("||") >= 2


class TestEscapeMdv2:
    def test_special_chars(self):
        for char in r"_*[]()~`>#+\-=|{}.!":
            result = _escape_mdv2(char)
            assert result == f"\\{char}", f"Failed for char: {char!r}"

    def test_normal_text_preserved(self):
        result = _escape_mdv2("hello world 123")
        assert result == "hello world 123"


class TestRenderExpandableQuote:
    def _make_match(self, text: str) -> re.Match[str]:
        start = re.escape(TranscriptParser.EXPANDABLE_QUOTE_START)
        end = re.escape(TranscriptParser.EXPANDABLE_QUOTE_END)
        pattern = re.compile(f"{start}([\\s\\S]*?){end}")
        full = f"{TranscriptParser.EXPANDABLE_QUOTE_START}{text}{TranscriptParser.EXPANDABLE_QUOTE_END}"
        m = pattern.search(full)
        assert m is not None
        return m

    def test_short_text(self):
        m = self._make_match("hello world")
        result = _render_expandable_quote(m)
        assert result.startswith(">")
        assert result.endswith("||")

    def test_long_text_truncated(self):
        m = self._make_match("x" * 5000)
        result = _render_expandable_quote(m)
        assert "truncated" in result
        assert len(result) <= 4000

    def test_multiline(self):
        m = self._make_match("line1\nline2\nline3")
        result = _render_expandable_quote(m)
        # Each line should be prefixed with >
        lines = result.split("\n")
        for line in lines:
            if line.strip():
                assert line.startswith(">")
