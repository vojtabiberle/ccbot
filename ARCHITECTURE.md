# Architecture

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Telegram Bot (bot.py)                       │
│  - Topic-based routing: 1 topic = 1 window = 1 session             │
│  - /history: Paginated message history (default: latest page)      │
│  - /screenshot: Capture pane as PNG                                │
│  - /esc: Send Escape to interrupt Claude                           │
│  - Send text → Claude Code via multiplexer keystrokes              │
│  - Forward /commands to Claude Code                                │
│  - Create sessions via directory browser in unbound topics         │
│  - Tool use → tool result: edit message in-place                   │
│  - Interactive UI: AskUserQuestion / ExitPlanMode / Permission     │
│  - Per-user message queue + worker (merge, rate limit)             │
│  - MarkdownV2 output with auto fallback to plain text              │
├──────────────────────┬──────────────────────────────────────────────┤
│  markdown_v2.py      │  telegram_sender.py                         │
│  MD → MarkdownV2     │  split_message (4096 limit)                 │
│  + expandable quotes │                                             │
├──────────────────────┴──────────────────────────────────────────────┤
│  terminal_parser.py                                                 │
│  - Detect interactive UIs (AskUserQuestion, ExitPlanMode, etc.)    │
│  - Parse status line (spinner + working text)                      │
└──────────┬──────────────────────────────┬───────────────────────────┘
           │                              │
           │ Notify (NewMessage callback) │ Send (multiplexer keys)
           │                              │
┌──────────┴──────────────┐    ┌──────────┴───────────────────────────┐
│  SessionMonitor         │    │  multiplexer/ package                │
│  (session_monitor.py)   │    │  __init__.py: get_mux() singleton    │
│  - Poll JSONL every 2s  │    │  base.py: MultiplexerBackend ABC     │
│  - Detect mtime changes │    │  tmux_backend.py: TmuxBackend        │
│  - Parse new lines      │    │  zellij_backend.py: ZellijBackend    │
│  - Track pending tools  │    │  - list/find/create/kill windows     │
│    across poll cycles   │    │  - send_keys / capture_pane          │
└──────────┬──────────────┘    └──────────────┬──────────────────────┘
           │                                  │
           ▼                                  ▼
┌────────────────────────┐         ┌─────────────────────────┐
│  TranscriptParser      │         │  Multiplexer Windows    │
│  (transcript_parser.py)│         │  (tmux windows or       │
│  - Parse JSONL entries │         │   Zellij tabs)          │
│  - Pair tool_use ↔     │         │  - Claude Code process  │
│    tool_result         │         │  - One window per       │
│  - Format expandable   │         │    topic/session        │
│    quotes for thinking │         └────────────┬────────────┘
│  - Extract history     │                      │
└────────────────────────┘              SessionStart hook
                                                │
                                                ▼
┌────────────────────────┐         ┌────────────────────────┐
│  SessionManager        │◄────────│  Hook (hook.py)        │
│  (session.py)          │  reads  │  - Auto-detect mux     │
│  - Window ↔ Session    │  map    │    (tmux or Zellij)    │
│    resolution          │         │  - Write session_map   │
│  - Thread bindings     │         │    .json               │
│    (topic → window)    │         └────────────────────────┘
│  - Message history     │
│    retrieval           │         ┌────────────────────────┐
└────────────────────────┘────────►│  Claude Sessions       │
                            reads  │  ~/.claude/projects/   │
┌────────────────────────┐  JSONL  │  - sessions-index      │
│  MonitorState          │         │  - *.jsonl files       │
│  (monitor_state.py)    │         └────────────────────────┘
│  - Track byte offset   │
│  - Prevent duplicates  │
│    after restart       │
└────────────────────────┘
```

## Data Mappings

**1 Topic = 1 Window = 1 Session:**

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│  Topic ID   │ ───▶ │ Window Name │ ───▶ │ Session ID  │
│  (Telegram) │      │ (mux window)│      │  (Claude)   │
└─────────────┘      └─────────────┘      └─────────────┘
     thread_bindings      session_map.json
     (state.json)         (written by hook)
```

**Mapping 1: Topic → Window (thread_bindings)**

```python
# session.py: SessionManager
thread_bindings: dict[int, dict[int, str]]  # user_id → {thread_id → window_name}
```

- Storage: memory + `~/.ccbot/state.json`
- Written when: user creates a new session via the directory browser in a topic
- Purpose: route user messages to the correct multiplexer window

**Mapping 2: Window → Session (session_map.json)**

```python
# session_map.json (key format: "mux_session:window_name")
{
  "ccbot:project": {"session_id": "uuid-xxx", "cwd": "/path/to/project"},
  "ccbot:project-2": {"session_id": "uuid-yyy", "cwd": "/path/to/project"}
}
```

- Storage: `~/.ccbot/session_map.json`
- Written when: Claude Code's `SessionStart` hook fires
- Property: one window maps to one session; session_id changes after `/clear`
- Purpose: SessionMonitor uses this mapping to decide which sessions to watch

## Message Flows

**Outbound (user → Claude):**

```
User sends "hello" in topic (thread_id=42)
    │
    ▼
thread_bindings[user_id][42] → "project"  (get bound window)
    │
    ▼
send_to_window("project", "hello")        (send to multiplexer)
```

**Inbound (Claude → user):**

```
SessionMonitor reads new message (session_id = "uuid-xxx")
    │
    ▼
Iterate thread_bindings, find (user, thread) whose window maps to this session
    │
    ▼
Deliver message to user in the correct topic (thread_id)
```

**New topic flow**: First message in an unbound topic → directory browser → select directory → create window → bind topic → forward pending message.

**Topic lifecycle**: Closing (or deleting) a topic auto-kills the associated multiplexer window and unbinds the thread. Stale bindings (window deleted externally) are cleaned up by the status polling loop.

## Session Lifecycle Management

Session monitor tracks window → session_id mappings via `session_map.json` (written by hook):

**Startup cleanup**: On bot startup, all tracked sessions not present in session_map are cleaned up, preventing monitoring of closed sessions.

**Runtime change detection**: Each polling cycle checks for session_map changes:
- Window's session_id changed (e.g., after `/clear`) → clean up old session
- Window deleted → clean up corresponding session

## Performance Optimizations

- **mtime cache**: The monitoring loop maintains an in-memory file mtime cache, skipping reads for unchanged files.
- **Byte offset incremental reads**: Each tracked session records `last_byte_offset`, reading only new content. File truncation (offset > file_size) is detected and offset is auto-reset.
- **Status deduplication**: The worker compares `last_text` when processing status updates; identical content skips the edit, reducing API calls.

## State Files (~/.ccbot/)

| File | Purpose |
|------|---------|
| `state.json` | Thread bindings + window states + read offsets |
| `session_map.json` | Hook-generated window→session mapping |
| `monitor_state.json` | Poll progress (byte offset) per JSONL file |

## Env Vars

| Var | Purpose |
|-----|---------|
| `MULTIPLEXER` | `"tmux"` (default) or `"zellij"` |
| `MUX_SESSION_NAME` | Session name (falls back to `TMUX_SESSION_NAME`, then `"ccbot"`) |

## Key Design Decisions

- **Topic-centric** — Each Telegram topic binds to one multiplexer window. No centralized session list; topics *are* the session list.
- **Window-centric** — All state anchored to window names (e.g. `myproject`), not directories. Same directory can have multiple windows (auto-suffixed: `myproject-2`). "Window" is the abstraction term (= tmux window = Zellij tab).
- **Pluggable multiplexer** — `MultiplexerBackend` ABC in `multiplexer/base.py`; `TmuxBackend` and `ZellijBackend` implementations; `get_mux()` singleton factory selected by `MULTIPLEXER` env var.
- **Hook-based session tracking** — Claude Code `SessionStart` hook auto-detects multiplexer (tmux or Zellij) and writes `session_map.json`; monitor reads it each poll cycle to auto-detect session changes.
- **Tool use ↔ tool result pairing** — `tool_use_id` tracked across poll cycles; tool result edits the original tool_use Telegram message in-place.
- **MarkdownV2 with fallback** — All messages go through `safe_reply`/`safe_edit`/`safe_send` which convert via `telegramify-markdown` and fall back to plain text on parse failure.
- **No truncation at parse layer** — Full content preserved; splitting at send layer respects Telegram's 4096 char limit with expandable quote atomicity.
- Only sessions registered in `session_map.json` (via hook) are monitored.
- Notifications delivered to users via thread bindings (topic → window → session).
