#!/usr/bin/env bash
set -euo pipefail

# Multiplexer backend: "tmux" (default) or "zellij"
MULTIPLEXER="${MULTIPLEXER:-tmux}"
MUX_SESSION="${MUX_SESSION_NAME:-${TMUX_SESSION_NAME:-ccbot}}"
MUX_WINDOW="__main__"
PROJECT_DIR="/data/code/ccbot"
MAX_WAIT=10  # seconds to wait for process to exit

# ── Tmux functions ───────────────────────────────────────────────────────

tmux_check_session() {
    if ! tmux has-session -t "$MUX_SESSION" 2>/dev/null; then
        echo "Error: tmux session '$MUX_SESSION' does not exist"
        exit 1
    fi
    if ! tmux list-windows -t "$MUX_SESSION" -F '#{window_name}' 2>/dev/null | grep -qx "$MUX_WINDOW"; then
        echo "Error: window '$MUX_WINDOW' not found in session '$MUX_SESSION'"
        exit 1
    fi
}

tmux_get_pane_pid() {
    tmux list-panes -t "${MUX_SESSION}:${MUX_WINDOW}" -F '#{pane_pid}'
}

tmux_send_ctrl_c() {
    tmux send-keys -t "${MUX_SESSION}:${MUX_WINDOW}" C-c
}

tmux_start_ccbot() {
    tmux send-keys -t "${MUX_SESSION}:${MUX_WINDOW}" "cd ${PROJECT_DIR} && uv run ccbot" Enter
}

tmux_capture_pane() {
    tmux capture-pane -t "${MUX_SESSION}:${MUX_WINDOW}" -p
}

# ── Zellij functions ─────────────────────────────────────────────────────

zellij_check_session() {
    if ! zellij list-sessions --short --no-formatting 2>/dev/null | grep -qx "$MUX_SESSION"; then
        echo "Error: zellij session '$MUX_SESSION' does not exist"
        echo "Create it first: zellij -s $MUX_SESSION"
        exit 1
    fi
}

zellij_get_pane_pid() {
    # Zellij doesn't expose pane PIDs easily; use pgrep as fallback
    pgrep -f 'uv.*run ccbot|ccbot.*\.venv/bin/ccbot' | head -1 || echo ""
}

zellij_send_ctrl_c() {
    zellij --session "$MUX_SESSION" action go-to-tab-name "$MUX_WINDOW" 2>/dev/null
    zellij --session "$MUX_SESSION" action write 3  # Ctrl-C = byte 3
}

zellij_start_ccbot() {
    zellij --session "$MUX_SESSION" action go-to-tab-name "$MUX_WINDOW" 2>/dev/null
    zellij --session "$MUX_SESSION" action write-chars "cd ${PROJECT_DIR} && uv run ccbot"
    sleep 0.5
    zellij --session "$MUX_SESSION" action write 13  # Enter
}

zellij_capture_pane() {
    local tmpfile="/tmp/ccbot_restart_capture.txt"
    zellij --session "$MUX_SESSION" action go-to-tab-name "$MUX_WINDOW" 2>/dev/null
    zellij --session "$MUX_SESSION" action dump-screen "$tmpfile" 2>/dev/null
    cat "$tmpfile" 2>/dev/null
    rm -f "$tmpfile"
}

# ── Dispatch based on multiplexer ────────────────────────────────────────

echo "Using multiplexer: $MULTIPLEXER (session: $MUX_SESSION, window: $MUX_WINDOW)"

if [ "$MULTIPLEXER" = "zellij" ]; then
    check_session() { zellij_check_session; }
    get_pane_pid() { zellij_get_pane_pid; }
    send_ctrl_c() { zellij_send_ctrl_c; }
    start_ccbot() { zellij_start_ccbot; }
    capture_pane() { zellij_capture_pane; }
else
    check_session() { tmux_check_session; }
    get_pane_pid() { tmux_get_pane_pid; }
    send_ctrl_c() { tmux_send_ctrl_c; }
    start_ccbot() { tmux_start_ccbot; }
    capture_pane() { tmux_capture_pane; }
fi

# ── Main logic ───────────────────────────────────────────────────────────

check_session

PANE_PID=$(get_pane_pid)

is_ccbot_running() {
    [ -n "$PANE_PID" ] && pstree -a "$PANE_PID" 2>/dev/null | grep -q 'uv.*run ccbot\|ccbot.*\.venv/bin/ccbot'
}

# Stop existing process if running
if is_ccbot_running; then
    echo "Found running ccbot process, sending Ctrl-C..."
    send_ctrl_c

    # Wait for process to exit
    waited=0
    while is_ccbot_running && [ "$waited" -lt "$MAX_WAIT" ]; do
        sleep 1
        waited=$((waited + 1))
        echo "  Waiting for process to exit... (${waited}s/${MAX_WAIT}s)"
    done

    if is_ccbot_running; then
        echo "Process did not exit after ${MAX_WAIT}s, sending SIGTERM..."
        UV_PID=$(pstree -ap "$PANE_PID" 2>/dev/null | grep -oP 'uv,\K\d+' | head -1)
        if [ -n "$UV_PID" ]; then
            kill "$UV_PID" 2>/dev/null || true
            sleep 2
        fi
        if is_ccbot_running; then
            echo "Process still running, sending SIGKILL..."
            kill -9 "$UV_PID" 2>/dev/null || true
            sleep 1
        fi
    fi

    echo "Process stopped."
else
    echo "No ccbot process running"
fi

# Brief pause to let the shell settle
sleep 1

# Start ccbot
echo "Starting ccbot..."
start_ccbot

# Verify startup and show logs
sleep 3
if is_ccbot_running; then
    echo "ccbot restarted successfully. Recent logs:"
    echo "----------------------------------------"
    capture_pane | tail -20
    echo "----------------------------------------"
else
    echo "Warning: ccbot may not have started. Pane output:"
    echo "----------------------------------------"
    capture_pane | tail -30
    echo "----------------------------------------"
    exit 1
fi
