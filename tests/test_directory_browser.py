"""Tests for ccbot.handlers.directory_browser — directory selection UI."""

from pathlib import Path

from ccbot.handlers.directory_browser import DIRS_PER_PAGE, build_directory_browser, clear_browse_state


class TestBuildDirectoryBrowser:
    def test_lists_subdirectories(self, tmp_path: Path):
        (tmp_path / "subdir1").mkdir()
        (tmp_path / "subdir2").mkdir()
        text, keyboard, subdirs = build_directory_browser(str(tmp_path))
        assert "subdir1" in subdirs
        assert "subdir2" in subdirs

    def test_hides_dotfiles(self, tmp_path: Path):
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "visible").mkdir()
        text, keyboard, subdirs = build_directory_browser(str(tmp_path))
        assert ".hidden" not in subdirs
        assert "visible" in subdirs

    def test_pagination(self, tmp_path: Path):
        for i in range(DIRS_PER_PAGE + 3):
            (tmp_path / f"dir{i:02d}").mkdir()
        text, keyboard, subdirs = build_directory_browser(str(tmp_path), page=0)
        # Should show nav buttons when more than one page
        # Check there are nav buttons in the keyboard
        all_cb: list[str] = [
            btn.callback_data for row in keyboard.inline_keyboard for btn in row
            if isinstance(btn.callback_data, str)
        ]
        # Should have page navigation
        has_page_nav = any("db:page:" in cb for cb in all_cb)
        assert has_page_nav

    def test_empty_dir(self, tmp_path: Path):
        text, keyboard, subdirs = build_directory_browser(str(tmp_path))
        assert subdirs == []
        assert "No subdirectories" in text

    def test_home_path_display(self):
        home = str(Path.home())
        text, keyboard, subdirs = build_directory_browser(home)
        assert "~" in text

    def test_select_and_cancel_buttons(self, tmp_path: Path):
        text, keyboard, subdirs = build_directory_browser(str(tmp_path))
        all_cb = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
        assert "db:confirm" in all_cb
        assert "db:cancel" in all_cb


class TestClearBrowseState:
    def test_clears_keys(self):
        user_data = {
            "state": "browsing_directory",
            "browse_path": "/tmp",
            "browse_page": 0,
            "browse_dirs": ["a", "b"],
            "other_key": "preserved",
        }
        clear_browse_state(user_data)
        assert "state" not in user_data
        assert "browse_path" not in user_data
        assert "browse_page" not in user_data
        assert "browse_dirs" not in user_data
        assert user_data["other_key"] == "preserved"

    def test_none_user_data(self):
        # Should not raise
        clear_browse_state(None)
