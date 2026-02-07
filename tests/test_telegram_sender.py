"""Tests for ccbot.telegram_sender — message splitting."""

from ccbot.telegram_sender import TELEGRAM_MAX_MESSAGE_LENGTH, split_message


class TestSplitMessage:
    def test_short_message_single_chunk(self):
        result = split_message("short text")
        assert result == ["short text"]

    def test_exact_limit(self):
        text = "a" * TELEGRAM_MAX_MESSAGE_LENGTH
        result = split_message(text)
        assert len(result) == 1
        assert result[0] == text

    def test_split_at_newlines(self):
        # Build text that exceeds limit, with newlines for splitting
        line = "x" * 100
        lines = [line] * 50  # 50 * 101 = 5050 chars
        text = "\n".join(lines)
        result = split_message(text)
        assert len(result) > 1
        # Each chunk should be <= max
        for chunk in result:
            assert len(chunk) <= TELEGRAM_MAX_MESSAGE_LENGTH

    def test_force_split_long_single_line(self):
        text = "a" * 10000  # No newlines
        result = split_message(text)
        assert len(result) > 1
        for chunk in result:
            assert len(chunk) <= TELEGRAM_MAX_MESSAGE_LENGTH

    def test_multiple_splits(self):
        # Create text needing 3+ chunks
        text = ("line\n") * 3000  # ~15000 chars
        result = split_message(text)
        assert len(result) >= 3

    def test_custom_max_length(self):
        text = "a" * 100
        result = split_message(text, max_length=30)
        assert len(result) > 1
        for chunk in result:
            assert len(chunk) <= 30

    def test_empty_message(self):
        result = split_message("")
        assert result == [""]

    def test_trailing_newlines_stripped(self):
        # Build text large enough to be split, with trailing newlines
        text = ("x" * 3000) + "\n" + ("y" * 3000) + "\n\n\n"
        result = split_message(text)
        assert len(result) >= 2
        # Each chunk has trailing newlines stripped by rstrip("\n")
        for chunk in result:
            assert not chunk.endswith("\n")

    def test_content_preservation(self):
        lines = ["line1", "line2", "line3"]
        text = "\n".join(lines)
        result = split_message(text)
        # Rejoining should give back the same content
        rejoined = "\n".join(result)
        assert rejoined == text

    def test_newline_boundary_preferred(self):
        # Build text where lines are each close to half the limit
        # so a split is forced between lines, not mid-line
        line_a = "a" * 3000
        line_b = "b" * 3000
        text = f"{line_a}\n{line_b}"
        result = split_message(text)
        assert len(result) == 2
        # First chunk should be just line_a (split at newline boundary)
        assert "b" not in result[0]
        assert "a" not in result[1]
