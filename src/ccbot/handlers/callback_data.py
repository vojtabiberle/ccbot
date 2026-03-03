"""Callback data constants for Telegram inline keyboards.

Defines all CB_* prefixes used for routing callback queries in the bot.
Each prefix identifies a specific action or navigation target.

Constants:
  - CB_HISTORY_*: History pagination
  - CB_DIR_*: Directory browser navigation
  - CB_SCREENSHOT_*: Screenshot refresh
  - CB_ASK_*: Interactive UI navigation (arrows, enter, esc)
  - CB_BIND_*: Bind existing window to topic
"""

# History pagination
CB_HISTORY_PREV = "hp:"  # history page older
CB_HISTORY_NEXT = "hn:"  # history page newer

# Directory browser
CB_DIR_SELECT = "db:sel:"
CB_DIR_UP = "db:up"
CB_DIR_CONFIRM = "db:confirm"
CB_DIR_CANCEL = "db:cancel"
CB_DIR_PAGE = "db:page:"

# Screenshot
CB_SCREENSHOT_REFRESH = "ss:ref:"

# Interactive UI (aq: prefix kept for backward compatibility)
CB_ASK_UP = "aq:up:"       # aq:up:<window>
CB_ASK_DOWN = "aq:down:"   # aq:down:<window>
CB_ASK_LEFT = "aq:left:"   # aq:left:<window>
CB_ASK_RIGHT = "aq:right:" # aq:right:<window>
CB_ASK_ESC = "aq:esc:"     # aq:esc:<window>
CB_ASK_ENTER = "aq:enter:" # aq:enter:<window>
CB_ASK_REFRESH = "aq:ref:" # aq:ref:<window>
CB_ASK_OPTION = "aq:opt:"  # aq:opt:<index>:<window>

# Suggestion prompt
CB_SUGGESTION_SEND = "sg:send:"  # sg:send:<window_name>

# Bind existing window
CB_BIND_SELECT = "bd:sel:"  # bd:sel:<window_name>

# Repo manager
CB_REPO_LIST = "rm:list"       # Show repo list (browser root)
CB_REPO_SELECT = "rm:sel:"     # Select a repo (payload: repo name)
CB_REPO_STATUS = "rm:st:"      # Show status (payload: repo name)
CB_REPO_UPDATE = "rm:up:"      # Update repo (payload: repo name)
CB_REPO_WTLIST = "rm:wt:"      # Show worktrees (payload: repo name)
CB_REPO_WTNEW = "rm:wn:"       # New worktree prompt (payload: repo name)
CB_REPO_WTSTART = "rm:ws:"     # Start Claude in worktree (payload: path encoded)
CB_REPO_PAGE = "rm:pg:"        # Pagination (payload: page number)
CB_REPO_BACK = "rm:back"       # Back to repo list

