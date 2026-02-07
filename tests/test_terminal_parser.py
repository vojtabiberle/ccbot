"""Tests for ccbot.terminal_parser — UI detection and status line parsing."""

from ccbot.terminal_parser import (
    extract_interactive_content,
    is_interactive_ui,
    parse_status_line,
)

from conftest import (
    PANE_ASK_USER_QUESTION,
    PANE_EXIT_PLAN_MODE,
    PANE_EXIT_PLAN_MODE_V2,
    PANE_PERMISSION_PROMPT,
    PANE_PLAIN_TEXT,
    PANE_RESTORE_CHECKPOINT,
    PANE_STATUS_DOT,
    PANE_STATUS_STAR,
)


# ── is_interactive_ui ────────────────────────────────────────────────────


class TestIsInteractiveUI:
    def test_ask_user_question(self):
        assert is_interactive_ui(PANE_ASK_USER_QUESTION) is True

    def test_exit_plan_mode(self):
        assert is_interactive_ui(PANE_EXIT_PLAN_MODE) is True

    def test_exit_plan_mode_v2(self):
        assert is_interactive_ui(PANE_EXIT_PLAN_MODE_V2) is True

    def test_permission_prompt(self):
        assert is_interactive_ui(PANE_PERMISSION_PROMPT) is True

    def test_restore_checkpoint(self):
        assert is_interactive_ui(PANE_RESTORE_CHECKPOINT) is True

    def test_plain_pane_false(self):
        assert is_interactive_ui(PANE_PLAIN_TEXT) is False


# ── extract_interactive_content ──────────────────────────────────────────


class TestExtractInteractiveContent:
    def test_ask_content_and_name(self):
        result = extract_interactive_content(PANE_ASK_USER_QUESTION)
        assert result is not None
        assert result.name == "AskUserQuestion"
        assert "Option A" in result.content

    def test_plan_content_and_name(self):
        result = extract_interactive_content(PANE_EXIT_PLAN_MODE)
        assert result is not None
        assert result.name == "ExitPlanMode"
        assert "plan description" in result.content

    def test_permission_content_and_name(self):
        result = extract_interactive_content(PANE_PERMISSION_PROMPT)
        assert result is not None
        assert result.name == "PermissionPrompt"
        assert "rm -rf" in result.content

    def test_empty_pane_none(self):
        assert extract_interactive_content("") is None

    def test_no_match_none(self):
        assert extract_interactive_content(PANE_PLAIN_TEXT) is None

    def test_long_separator_shortening(self):
        # _shorten_separators only shortens lines that are EXACTLY dashes (no leading spaces)
        pane = (
            "  Would you like to proceed?\n"
            "\n"
            "──────────────────────────────────────\n"
            "  Some plan content\n"
            "\n"
            "  ctrl-g to edit in editor\n"
        )
        result = extract_interactive_content(pane)
        assert result is not None
        # Long separator lines (matching ^─{5,}$) should be shortened to ─────
        assert "─────" in result.content
        assert "──────────────────────────────────────" not in result.content


# ── parse_status_line ────────────────────────────────────────────────────


class TestParseStatusLine:
    def test_dot_spinner(self):
        result = parse_status_line(PANE_STATUS_DOT)
        assert result is not None
        assert "Reading files" in result

    def test_star_spinner(self):
        result = parse_status_line(PANE_STATUS_STAR)
        assert result is not None
        assert "Working on task" in result

    def test_all_spinner_chars(self):
        for char in ["·", "✻", "✽", "✶", "✳", "✢"]:
            pane = f"some output\n{char} Doing work"
            result = parse_status_line(pane)
            assert result is not None, f"Spinner {char!r} not detected"
            assert "Doing work" in result

    def test_no_spinner_none(self):
        result = parse_status_line(PANE_PLAIN_TEXT)
        assert result is None

    def test_empty_none(self):
        assert parse_status_line("") is None

    def test_scans_bottom_15_lines(self):
        # Status line within bottom 15 lines should be found
        lines = ["line"] * 20 + ["✻ Found it"]
        pane = "\n".join(lines)
        result = parse_status_line(pane)
        assert result is not None
        assert "Found it" in result

    def test_strips_spinner_char(self):
        pane = "some text\n✶ My status"
        result = parse_status_line(pane)
        assert result == "My status"

    def test_status_beyond_15_lines_not_found(self):
        # Status line beyond bottom 15 lines should NOT be found
        lines = ["✻ Hidden status"] + ["line"] * 20
        pane = "\n".join(lines)
        result = parse_status_line(pane)
        assert result is None
