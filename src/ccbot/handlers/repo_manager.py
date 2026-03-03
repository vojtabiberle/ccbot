"""Telegram handlers for repo-manager integration.

Provides:
  - /repo <add|update|status> — CLI-style subcommands
  - /repos — interactive repo browser with inline keyboards
  - /wt <repo> <branch> [source] — create worktree + Claude session

Callback routing (all ``rm:`` prefixes) is handled by
:func:`callback_repo_handler`, wired into the main callback dispatcher
in ``bot.py``.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ccbot.handlers.callback_data import (
    CB_REPO_BACK,
    CB_REPO_LIST,
    CB_REPO_PAGE,
    CB_REPO_SELECT,
    CB_REPO_STATUS,
    CB_REPO_UPDATE,
    CB_REPO_WTNEW,
    CB_REPO_WTLIST,
    CB_REPO_WTSTART,
)
from ccbot.handlers.message_sender import safe_edit, safe_reply
from ccbot.multiplexer import get_mux
from ccbot.repo_client import RepoInfo, RepoStatus, repo_client
from ccbot.session import session_manager

logger = logging.getLogger(__name__)

# Pagination
REPOS_PER_PAGE = 8
REPOS_PER_ROW = 2


# -------------------------------------------------------------------
# Formatting helpers
# -------------------------------------------------------------------

def _format_status(status: RepoStatus) -> str:
    """Emoji-rich single-repo status block."""
    dirty_icon = "\u26a0\ufe0f" if status.dirty else "\u2705"
    sync = ""
    if status.ahead:
        sync += f" \u2b06 {status.ahead}"
    if status.behind:
        sync += f" \u2b07 {status.behind}"
    if not sync:
        sync = " \u2705 in sync"

    lines = [
        f"*{status.name}*",
        f"Branch: `{status.branch}` {dirty_icon}{sync}",
        f"Last commit: {status.last_commit}",
        f"Date: {status.last_commit_date}",
    ]
    if status.url:
        lines.append(f"URL: `{status.url}`")
    return "\n".join(lines)


def _format_repo_list(repos: list[RepoInfo]) -> str:
    """Short plain-text summary for the browser header."""
    if not repos:
        return "No repositories registered."
    return f"*Repositories* ({len(repos)})\n\nSelect a repo to manage:"


# -------------------------------------------------------------------
# Keyboard builders
# -------------------------------------------------------------------

def _build_repo_keyboard(
    repos: list[RepoInfo], page: int = 0,
) -> InlineKeyboardMarkup:
    """Build paginated inline keyboard of repo names."""
    total_pages = max(1, (len(repos) + REPOS_PER_PAGE - 1) // REPOS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start = page * REPOS_PER_PAGE
    page_repos = repos[start : start + REPOS_PER_PAGE]

    buttons: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(page_repos), REPOS_PER_ROW):
        row: list[InlineKeyboardButton] = []
        for repo in page_repos[i : i + REPOS_PER_ROW]:
            dirty = " \u26a0\ufe0f" if repo.dirty else ""
            label = repo.name[:18] + "\u2026" if len(repo.name) > 19 else repo.name
            row.append(InlineKeyboardButton(
                f"{label}{dirty}",
                callback_data=f"{CB_REPO_SELECT}{repo.name}"[:64],
            ))
        buttons.append(row)

    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                "\u25c0", callback_data=f"{CB_REPO_PAGE}{page - 1}",
            ))
        nav.append(InlineKeyboardButton(
            f"{page + 1}/{total_pages}", callback_data="noop",
        ))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(
                "\u25b6", callback_data=f"{CB_REPO_PAGE}{page + 1}",
            ))
        buttons.append(nav)

    return InlineKeyboardMarkup(buttons)


def _build_action_keyboard(repo_name: str) -> InlineKeyboardMarkup:
    """Action menu for a selected repo."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "Status", callback_data=f"{CB_REPO_STATUS}{repo_name}"[:64],
            ),
            InlineKeyboardButton(
                "Update", callback_data=f"{CB_REPO_UPDATE}{repo_name}"[:64],
            ),
        ],
        [
            InlineKeyboardButton(
                "Worktrees", callback_data=f"{CB_REPO_WTLIST}{repo_name}"[:64],
            ),
        ],
        [
            InlineKeyboardButton(
                "\u00ab Back", callback_data=CB_REPO_BACK,
            ),
        ],
    ])


def _build_wt_keyboard(
    repo_name: str, worktrees: list,
) -> InlineKeyboardMarkup:
    """Worktree list with optional launch buttons."""
    buttons: list[list[InlineKeyboardButton]] = []
    for wt in worktrees:
        label = wt.branch[:20] + "\u2026" if len(wt.branch) > 21 else wt.branch
        buttons.append([InlineKeyboardButton(
            f"\U0001f333 {label}",
            callback_data=f"{CB_REPO_WTSTART}{wt.path}"[:64],
        )])

    buttons.append([InlineKeyboardButton(
        "+ New Worktree",
        callback_data=f"{CB_REPO_WTNEW}{repo_name}"[:64],
    )])
    buttons.append([InlineKeyboardButton(
        "\u00ab Back",
        callback_data=f"{CB_REPO_SELECT}{repo_name}"[:64],
    )])
    return InlineKeyboardMarkup(buttons)


# -------------------------------------------------------------------
# Command handlers
# -------------------------------------------------------------------

async def cmd_repo(
    update: Update, context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle ``/repo <subcommand> [args]``."""
    msg = update.effective_message
    if not msg:
        return

    args = context.args or []
    if not args:
        await safe_reply(msg, "Usage: `/repo add <url> [name]`\n`/repo update [name]`\n`/repo status [name]`")
        return

    sub = args[0].lower()

    if sub == "add":
        if len(args) < 2:
            await safe_reply(msg, "Usage: `/repo add <url> [name]`")
            return
        url = args[1]
        name = args[2] if len(args) > 2 else None
        try:
            path = await repo_client.add_repo(url, name)
            await safe_reply(msg, f"\u2705 Repo added: `{path}`")
        except RuntimeError as e:
            await safe_reply(msg, f"\u274c Failed: {e}")

    elif sub == "update":
        name = args[1] if len(args) > 1 else None
        try:
            results = await repo_client.update_repos(name)
            if not results:
                await safe_reply(msg, "\u2705 Nothing to update.")
                return
            lines = [f"`{n}` \u2014 {s}" for n, s in results]
            await safe_reply(msg, "*Update results:*\n\n" + "\n".join(lines))
        except RuntimeError as e:
            await safe_reply(msg, f"\u274c Failed: {e}")

    elif sub == "status":
        name = args[1] if len(args) > 1 else None
        try:
            result = await repo_client.status(name)
            if isinstance(result, list):
                text = "\n\n---\n\n".join(_format_status(s) for s in result)
            else:
                text = _format_status(result)
            await safe_reply(msg, text)
        except RuntimeError as e:
            await safe_reply(msg, f"\u274c Failed: {e}")

    else:
        await safe_reply(msg, f"Unknown subcommand: `{sub}`")


async def cmd_repos(
    update: Update, context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle ``/repos`` — show interactive repo browser."""
    msg = update.effective_message
    if not msg:
        return

    try:
        repos = await repo_client.list_repos()
    except RuntimeError as e:
        await safe_reply(msg, f"\u274c Failed: {e}")
        return

    text = _format_repo_list(repos)
    keyboard = _build_repo_keyboard(repos) if repos else None
    await safe_reply(msg, text, reply_markup=keyboard)


async def cmd_wt(
    update: Update, context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle ``/wt <repo> <branch> [source]`` — create worktree + Claude session."""
    msg = update.effective_message
    if not msg:
        return

    args = context.args or []
    if len(args) < 2:
        await safe_reply(msg, "Usage: `/wt <repo> <branch> [source]`")
        return

    repo_name = args[0]
    branch = args[1]
    source = args[2] if len(args) > 2 else None

    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is None:
        return

    thread_id = msg.message_thread_id

    # 1. Create worktree
    try:
        wt_path = await repo_client.wt_add(repo_name, branch, source)
    except RuntimeError as e:
        await safe_reply(msg, f"\u274c Worktree creation failed: {e}")
        return

    await safe_reply(msg, f"\U0001f333 Worktree created: `{wt_path}`\nStarting Claude session\u2026")

    # 2. Create mux window
    success, message, window_name = await get_mux().create_window(wt_path)
    if not success:
        await safe_reply(msg, f"\u274c Window creation failed: {message}")
        return

    # 3. Wait for session map
    old_state = session_manager.window_states.get(window_name)
    old_sid = old_state.session_id if old_state else None
    await session_manager.wait_for_session_map_entry(
        window_name, exclude_session_id=old_sid,
    )

    # 4. Bind to topic if in a thread
    if thread_id is not None:
        session_manager.bind_thread(chat_id, thread_id, window_name)
        try:
            await context.bot.edit_forum_topic(
                chat_id=chat_id,
                message_thread_id=thread_id,
                name=window_name,
            )
        except Exception as e:
            logger.debug("Failed to rename topic: %s", e)
        await safe_reply(
            msg,
            f"\u2705 Session `{window_name}` bound to this topic.",
        )
    else:
        await safe_reply(
            msg,
            f"\u2705 Session `{window_name}` started in `{wt_path}`.",
        )


# -------------------------------------------------------------------
# Callback handler
# -------------------------------------------------------------------

async def callback_repo_handler(
    query, data: str, chat_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Route all ``rm:`` callback queries.

    Called from the main ``callback_handler`` in ``bot.py``.
    """

    # --- Repo list / back ---
    if data == CB_REPO_LIST or data == CB_REPO_BACK:
        try:
            repos = await repo_client.list_repos()
        except RuntimeError as e:
            await safe_edit(query, f"\u274c {e}")
            await query.answer()
            return
        text = _format_repo_list(repos)
        keyboard = _build_repo_keyboard(repos) if repos else None
        await safe_edit(query, text, reply_markup=keyboard)
        await query.answer()

    # --- Select a repo ---
    elif data.startswith(CB_REPO_SELECT):
        repo_name = data[len(CB_REPO_SELECT):]
        keyboard = _build_action_keyboard(repo_name)
        await safe_edit(query, f"*{repo_name}*\n\nChoose an action:", reply_markup=keyboard)
        await query.answer()

    # --- Status ---
    elif data.startswith(CB_REPO_STATUS):
        repo_name = data[len(CB_REPO_STATUS):]
        try:
            result = await repo_client.status(repo_name)
            if isinstance(result, list):
                text = "\n\n".join(_format_status(s) for s in result)
            else:
                text = _format_status(result)
        except RuntimeError as e:
            text = f"\u274c {e}"
        back_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("\u00ab Back", callback_data=f"{CB_REPO_SELECT}{repo_name}"[:64]),
        ]])
        await safe_edit(query, text, reply_markup=back_kb)
        await query.answer()

    # --- Update ---
    elif data.startswith(CB_REPO_UPDATE):
        repo_name = data[len(CB_REPO_UPDATE):]
        await query.answer("Updating\u2026")
        try:
            results = await repo_client.update_repos(repo_name)
            if not results:
                text = f"\u2705 `{repo_name}` is up to date."
            else:
                lines = [f"`{n}` \u2014 {s}" for n, s in results]
                text = "*Update:*\n\n" + "\n".join(lines)
        except RuntimeError as e:
            text = f"\u274c {e}"
        back_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("\u00ab Back", callback_data=f"{CB_REPO_SELECT}{repo_name}"[:64]),
        ]])
        await safe_edit(query, text, reply_markup=back_kb)

    # --- Worktree list ---
    elif data.startswith(CB_REPO_WTLIST):
        repo_name = data[len(CB_REPO_WTLIST):]
        try:
            worktrees = await repo_client.wt_list(repo_name)
        except RuntimeError as e:
            await safe_edit(query, f"\u274c {e}")
            await query.answer()
            return
        if not worktrees:
            text = f"*{repo_name}* \u2014 No worktrees.\n\nUse `/wt {repo_name} <branch>` to create one."
        else:
            text = f"*{repo_name}* \u2014 Worktrees ({len(worktrees)}):"
        keyboard = _build_wt_keyboard(repo_name, worktrees)
        await safe_edit(query, text, reply_markup=keyboard)
        await query.answer()

    # --- New worktree prompt ---
    elif data.startswith(CB_REPO_WTNEW):
        repo_name = data[len(CB_REPO_WTNEW):]
        await safe_edit(
            query,
            f"To create a new worktree, use:\n\n`/wt {repo_name} <branch> [source]`",
        )
        await query.answer()

    # --- Start Claude in worktree ---
    elif data.startswith(CB_REPO_WTSTART):
        wt_path = data[len(CB_REPO_WTSTART):]
        await query.answer("Starting\u2026")

        success, message, window_name = await get_mux().create_window(wt_path)
        if not success:
            await safe_edit(query, f"\u274c {message}")
            return

        old_state = session_manager.window_states.get(window_name)
        old_sid = old_state.session_id if old_state else None
        await session_manager.wait_for_session_map_entry(
            window_name, exclude_session_id=old_sid,
        )

        thread_id: int | None = None
        m = update.callback_query.message if update.callback_query else None
        if m:
            thread_id = m.message_thread_id

        if thread_id is not None:
            session_manager.bind_thread(chat_id, thread_id, window_name)
            try:
                await context.bot.edit_forum_topic(
                    chat_id=chat_id,
                    message_thread_id=thread_id,
                    name=window_name,
                )
            except Exception as e:
                logger.debug("Failed to rename topic: %s", e)
            await safe_edit(
                query,
                f"\u2705 Session `{window_name}` bound to this topic.",
            )
        else:
            await safe_edit(
                query,
                f"\u2705 Session `{window_name}` started in `{wt_path}`.",
            )

    # --- Pagination ---
    elif data.startswith(CB_REPO_PAGE):
        page_str = data[len(CB_REPO_PAGE):]
        try:
            page = int(page_str)
        except ValueError:
            await query.answer("Invalid page")
            return
        try:
            repos = await repo_client.list_repos()
        except RuntimeError as e:
            await safe_edit(query, f"\u274c {e}")
            await query.answer()
            return
        text = _format_repo_list(repos)
        keyboard = _build_repo_keyboard(repos, page=page) if repos else None
        await safe_edit(query, text, reply_markup=keyboard)
        await query.answer()
