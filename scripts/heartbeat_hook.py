#!/usr/bin/env python3
"""Stop hook — heartbeat + guardian IPC + workflow engine intelligence capture."""
import sys, os, json
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 1. Notify guardian daemon
try:
    from guardian_client import notify_session_stop
    notify_session_stop(0)
except Exception:
    pass

# 2. Heartbeat memory forest (legacy)
try:
    from memory_forest import heartbeat_all, gc_check, _today
    changes = heartbeat_all(dry_run=False)
    if changes:
        for c in changes:
            print(c, file=sys.stderr)
    eligible = gc_check()
    if eligible:
        urgent = [e for e in eligible if e["node"]["frontmatter"].get("layer") in ("L1",)]
        if urgent:
            print(f"[{_today()}] GC: {len(eligible)} candidates ({len(urgent)} urgent)", file=sys.stderr)
    print(f"记忆森林: heartbeat={_today()}", file=sys.stderr)
except Exception:
    pass

# 3. Trigger workflow engine session-end capture (fire-and-forget)
try:
    req = Request("http://localhost:8900/workflow/session-end",
                  data=json.dumps({"dry_run": False}).encode(),
                  headers={"Content-Type": "application/json"},
                  method="POST")
    urlopen(req, timeout=10)
except Exception:
    pass
