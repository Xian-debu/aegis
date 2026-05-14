"""IPC client for Claude hooks to communicate with Claude Guardian daemon.

Usage from hooks:
    from guardian_client import notify_session_start, notify_heartbeat, notify_session_stop
    notify_session_start()
    notify_heartbeat("Bash")
    notify_session_stop(0)
"""
import json
import os
import socket
import time

SOCKET_PATH = "/root/.claude/guardian/guardian.sock"


def _get_session_id() -> str:
    """Read session ID from environment at call time, not import time."""
    return os.environ.get("CLAUDE_SESSION_ID", "")


def _send(msg: dict):
    """Send a JSON message to the guardian daemon. Fire-and-forget."""
    sid = _get_session_id()
    if not sid:
        return
    msg.setdefault("session_id", sid)
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(SOCKET_PATH)
        sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))
        sock.close()
    except (FileNotFoundError, ConnectionRefusedError, socket.timeout):
        pass  # Guardian not running — silent fail


def notify_session_start():
    """Called by SessionStart hook."""
    _send({
        "type": "session_start",
        "pid": os.getpid(),
        "cwd": os.getcwd(),
    })


def notify_heartbeat(tool_name: str = ""):
    """Called by PreToolUse hook. Reports tool activity."""
    _send({
        "type": "heartbeat",
        "tool_name": tool_name,
        "cwd": os.getcwd(),
    })


def notify_session_stop(exit_code: int = 0, summary: str = ""):
    """Called by Stop hook."""
    _send({
        "type": "session_stop",
        "exit_code": exit_code,
        "summary": summary,
    })


def guardian_running() -> bool:
    """Check if guardian daemon is reachable."""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(1)
        sock.connect(SOCKET_PATH)
        sock.close()
        return True
    except (FileNotFoundError, ConnectionRefusedError, socket.timeout):
        return False
