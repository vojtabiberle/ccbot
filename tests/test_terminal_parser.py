"""Tests for ccbot.terminal_parser — UI detection and status line parsing."""

from ccbot.terminal_parser import (
    extract_interactive_content,
    is_interactive_ui,
    parse_cursor_index,
    parse_options,
    parse_status_line,
)

from conftest import (
    PANE_ASK_USER_QUESTION,
    PANE_EXIT_PLAN_MODE,
    PANE_EXIT_PLAN_MODE_V2,
    PANE_PERMISSION_PROMPT,
    PANE_PERMISSION_PROMPT_V2,
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

    def test_permission_prompt_v2(self):
        assert is_interactive_ui(PANE_PERMISSION_PROMPT_V2) is True

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

    def test_permission_v2_content_and_name(self):
        result = extract_interactive_content(PANE_PERMISSION_PROMPT_V2)
        assert result is not None
        assert result.name == "PermissionPrompt"
        assert "src/config.py" in result.content

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


# ── parse_options ──────────────────────────────────────────────────────


class TestParseOptions:
    def test_checkbox_options(self):
        content = "  ☐ Option A\n  ☐ Option B\n  ☐ Option C (Recommended)"
        assert parse_options(content) == [
            "Option A", "Option B", "Option C (Recommended)",
        ]

    def test_checked_checkbox(self):
        content = "  ☑ Selected\n  ☐ Not selected"
        assert parse_options(content) == ["Selected", "Not selected"]

    def test_checkmark(self):
        content = "  ✓ Done item\n  ☐ Pending item"
        assert parse_options(content) == ["Done item", "Pending item"]

    def test_numbered_options(self):
        content = "  ❯ 1. Yes\n    2. No\n    3. Maybe"
        assert parse_options(content) == ["Yes", "No", "Maybe"]

    def test_numbered_without_arrow(self):
        content = "  1. First option\n  2. Second option"
        assert parse_options(content) == ["First option", "Second option"]

    def test_permission_prompt_v2(self):
        content = (
            "  Do you want to make this edit to src/config.py?\n"
            "\n"
            "  ❯ 1. Yes\n"
            "    2. Yes, allow all edits in project/ during this session (shift+tab)\n"
            "    3. No\n"
            "\n"
            "  Enter confirm · Esc cancel"
        )
        assert parse_options(content) == [
            "Yes",
            "Yes, allow all edits in project/ during this session (shift+tab)",
            "No",
        ]

    def test_no_options(self):
        content = "Just some text\nwith no options"
        assert parse_options(content) == []

    def test_empty_string(self):
        assert parse_options("") == []

    def test_mixed_ignored(self):
        # Lines that don't match any pattern are skipped
        content = "Question text\n  ☐ Option A\nMore text\n  ☐ Option B"
        assert parse_options(content) == ["Option A", "Option B"]

    def test_ask_user_question_pane(self):
        result = parse_options(PANE_ASK_USER_QUESTION)
        assert result == ["Option A", "Option B", "Option C (Recommended)"]

    def test_permission_prompt_v2_pane(self):
        result = parse_options(PANE_PERMISSION_PROMPT_V2)
        assert "Yes" in result
        assert "No" in result


# ── parse_cursor_index ─────────────────────────────────────────────────


class TestParseCursorIndex:
    def test_cursor_on_first_numbered(self):
        content = "  ❯ 1. Yes\n    2. No\n    3. Maybe"
        assert parse_cursor_index(content) == 0

    def test_cursor_on_second_numbered(self):
        content = "    1. Yes\n  ❯ 2. No\n    3. Maybe"
        assert parse_cursor_index(content) == 1

    def test_cursor_on_third_numbered(self):
        content = "    1. Yes\n    2. No\n  ❯ 3. Maybe"
        assert parse_cursor_index(content) == 2

    def test_no_cursor_defaults_to_zero(self):
        content = "  ☐ Option A\n  ☐ Option B"
        assert parse_cursor_index(content) == 0

    def test_permission_prompt_v2_default(self):
        # ❯ is on option 1 (index 0)
        assert parse_cursor_index(PANE_PERMISSION_PROMPT_V2) == 0

    def test_no_options_returns_zero(self):
        assert parse_cursor_index("Just some text") == 0

    def test_empty_returns_zero(self):
        assert parse_cursor_index("") == 0
