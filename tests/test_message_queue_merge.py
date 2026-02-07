"""Tests for ccbot.handlers.message_queue — merge eligibility logic."""

from ccbot.handlers.message_queue import MERGE_MAX_LENGTH, MessageTask, _can_merge_tasks


def _content_task(
    window: str = "proj",
    content_type: str = "text",
    parts: list[str] | None = None,
) -> MessageTask:
    return MessageTask(
        task_type="content",
        window_name=window,
        content_type=content_type,
        parts=parts or ["hello"],
    )


def _status_task(window: str = "proj") -> MessageTask:
    return MessageTask(
        task_type="status_update",
        window_name=window,
        text="status",
    )


class TestCanMergeTasks:
    def test_merge_same_window_text(self):
        base = _content_task("proj", "text")
        candidate = _content_task("proj", "text")
        assert _can_merge_tasks(base, candidate) is True

    def test_no_merge_different_windows(self):
        base = _content_task("proj1", "text")
        candidate = _content_task("proj2", "text")
        assert _can_merge_tasks(base, candidate) is False

    def test_no_merge_tool_use_base(self):
        base = _content_task("proj", "tool_use")
        candidate = _content_task("proj", "text")
        assert _can_merge_tasks(base, candidate) is False

    def test_no_merge_tool_result_base(self):
        base = _content_task("proj", "tool_result")
        candidate = _content_task("proj", "text")
        assert _can_merge_tasks(base, candidate) is False

    def test_no_merge_tool_use_candidate(self):
        base = _content_task("proj", "text")
        candidate = _content_task("proj", "tool_use")
        assert _can_merge_tasks(base, candidate) is False

    def test_no_merge_tool_result_candidate(self):
        base = _content_task("proj", "text")
        candidate = _content_task("proj", "tool_result")
        assert _can_merge_tasks(base, candidate) is False

    def test_no_merge_status_task(self):
        base = _content_task("proj", "text")
        candidate = _status_task("proj")
        assert _can_merge_tasks(base, candidate) is False

    def test_merge_thinking_tasks(self):
        base = _content_task("proj", "thinking")
        candidate = _content_task("proj", "thinking")
        assert _can_merge_tasks(base, candidate) is True


class TestMessageTaskDefaults:
    def test_default_fields(self):
        task = MessageTask(task_type="content")
        assert task.text is None
        assert task.window_name is None
        assert task.parts == []
        assert task.tool_use_id is None
        assert task.content_type == "text"
        assert task.thread_id is None


class TestMergeMaxLength:
    def test_constant_value(self):
        assert MERGE_MAX_LENGTH == 3800
