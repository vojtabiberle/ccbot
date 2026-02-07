"""Tests for ccbot.screenshot — text to PNG rendering."""

import pytest

from ccbot.screenshot import (
    _approximate_256_color,
    _font_tier,
    text_to_image,
)


class TestTextToImage:
    @pytest.mark.asyncio
    async def test_valid_png_output(self):
        result = await text_to_image("Hello World")
        assert isinstance(result, bytes)
        # PNG magic bytes
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    @pytest.mark.asyncio
    async def test_empty_text_valid_image(self):
        result = await text_to_image("")
        assert isinstance(result, bytes)
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    @pytest.mark.asyncio
    async def test_ansi_colors_produce_different_bytes(self):
        plain = await text_to_image("Hello", with_ansi=False)
        colored = await text_to_image("\x1b[31mHello\x1b[0m", with_ansi=True)
        # Both should be valid PNGs
        assert plain[:4] == b"\x89PNG"
        assert colored[:4] == b"\x89PNG"
        # Different content should produce different images
        assert plain != colored

    @pytest.mark.asyncio
    async def test_multiline_produces_taller_image(self):
        one_line = await text_to_image("line1")
        three_lines = await text_to_image("line1\nline2\nline3")
        # Both valid PNGs, three-line version should be larger
        assert len(three_lines) > len(one_line)


class TestFontTier:
    def test_ascii_is_tier_0(self):
        assert _font_tier("A") == 0
        assert _font_tier("z") == 0
        assert _font_tier("5") == 0

    def test_cjk_is_tier_1(self):
        assert _font_tier("\u4e2d") == 1  # 中

    def test_symbola_is_tier_2(self):
        assert _font_tier("\u2714") == 2  # ✔


class TestApproximate256Color:
    def test_basic_16_colors(self):
        for i in range(16):
            result = _approximate_256_color(i)
            assert isinstance(result, tuple)
            assert len(result) == 3

    def test_216_color_cube(self):
        result = _approximate_256_color(16)  # First cube color
        assert isinstance(result, tuple)
        assert result == (0, 0, 0)

    def test_grayscale(self):
        result = _approximate_256_color(232)  # First grayscale
        assert isinstance(result, tuple)
        assert result[0] == result[1] == result[2]  # Should be gray
