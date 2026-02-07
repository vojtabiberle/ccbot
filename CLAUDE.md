# CLAUDE.md

For detailed architecture, diagrams, data mappings, and message flows see [ARCHITECTURE.md](ARCHITECTURE.md).

## Development Rules

### Code Quality

- Run `pyright src/ccbot/` after every code change. Ensure 0 errors before committing.
- Every Python source file must start with a module-level docstring (`"""..."""`). First line = one-sentence summary; subsequent lines = responsibilities, key components, module relationships. Update when core features change.

### Telegram Conventions

- All messages use `parse_mode="MarkdownV2"` via `telegramify-markdown`. Use `safe_reply`/`safe_edit`/`safe_send` helpers (auto-convert + plain text fallback). Internal queue/UI code (`message_queue.py`, `interactive_ui.py`) calls Telegram API directly with its own fallback.
- Prefer inline keyboards over reply keyboards; use `edit_message_text` for in-place updates; keep callback data under 64 bytes; use `answer_callback_query` for instant feedback.
- Flood control: minimum 1.1s between messages per user. Outbound messages go through `rate_limit_send()`.

### Core Abstractions

- **Window as the core unit**: all logic operates on multiplexer windows (tmux window = Zellij tab), not directories. Window names default to directory name with auto-suffix (e.g., `project-2`).
- **Topic-only architecture**: 1 Topic = 1 Window = 1 Session. No `active_sessions`, no `/list` command, no General topic routing, no backward-compatibility for non-topic modes.
- **No message truncation**: full content preserved at parse layer. Splitting only at send layer (`split_message`, 4096-char limit).
- `/history` defaults to the last page (newest messages).

### Message Queue & Delivery

- Per-user FIFO queues. Consecutive content messages for the same window are merged (up to 3800 chars).
- `tool_use` breaks the merge chain (sent separately, message ID recorded). `tool_result` is edited into the `tool_use` message.
- Status messages are edited into the first content message to reduce message count.

### Multiplexer Backend

- `MULTIPLEXER=tmux` (default) or `MULTIPLEXER=zellij`. Session name: `MUX_SESSION_NAME` (falls back to `TMUX_SESSION_NAME`, then `"ccbot"`).
- Zellij limitations: no ANSI color capture, session must pre-exist, focus ops serialized via asyncio.Lock.

### Operations

- Restart service: `./scripts/restart.sh`
- Install hook: `ccbot hook --install`
