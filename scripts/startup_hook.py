#!/usr/bin/env python3
"""SessionStart hook — system drive + guardian IPC + workflow engine."""
import sys, os, json
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 1. Notify guardian daemon
try:
    from guardian_client import notify_session_start
    notify_session_start()
except Exception:
    pass

# 2. Generate context injection for session prompt
try:
    from system_drive import cmd_session_start
    cmd_session_start()
except Exception:
    pass

# 3. Trigger workflow engine (fire-and-forget, non-blocking)
try:
    req = Request("http://localhost:8900/workflow/session-start",
                  data=json.dumps({"dry_run": False}).encode(),
                  headers={"Content-Type": "application/json"},
                  method="POST")
    urlopen(req, timeout=5)
except Exception:
    pass
