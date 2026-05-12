"""Bridge L3: Claude Guardian ↔ RAG Knowledge Base.

Guardian→KB: Health snapshots → KB documents, session summaries → indexed
KB→Guardian: KB can query system state, search health history
"""
import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from aegis.config import GUARDIAN_DB, KB_ROOT, AUTO_HEALTH_TO_KB

sys.path.insert(0, str(KB_ROOT))
sys.path.insert(0, "/root/.claude/scripts")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Guardian DB access ─────────────────────────────────

def _guardian_query(sql: str, params: tuple = ()) -> list[dict]:
    if not GUARDIAN_DB.exists():
        return []
    conn = sqlite3.connect(f"file:{GUARDIAN_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Health snapshots → KB ─────────────────────────────

def index_health_snapshots(limit: int = 10) -> dict:
    """Index recent Guardian health snapshots into KB as searchable documents.

    Returns {indexed: int, errors: [str]}
    """
    result = {"indexed": 0, "errors": []}

    if not AUTO_HEALTH_TO_KB:
        return result

    snapshots = _guardian_query(
        "SELECT * FROM health_snapshots ORDER BY id DESC LIMIT ?", (limit,)
    )

    for snap in snapshots:
        text = _format_health_snapshot(snap)
        title = f"Health Snapshot {snap.get('timestamp', '?')[:16]}"

        try:
            r = subprocess.run(
                [sys.executable or "python3", str(KB_ROOT / "scripts" / "kb_cli.py"),
                 "ingest", "--title", title, "--tags", "health,system,auto-generated",
                 "--format", "text", "-"],
                input=text.encode("utf-8"),
                capture_output=True, text=True, timeout=30,
            )
            if "Ingested:" in r.stdout or "Already exists" in r.stdout:
                result["indexed"] += 1
            else:
                result["errors"].append(r.stderr.strip()[:200])
        except Exception as e:
            result["errors"].append(str(e))

    return result


def _format_health_snapshot(snap: dict) -> str:
    """Format a health snapshot row into readable text."""
    return f"""System Health Snapshot
Timestamp: {snap.get('timestamp', '?')}
Disk: {snap.get('disk_pct', '?')}%
Memory: {snap.get('mem_used_gb', '?')}/{snap.get('mem_total_gb', '?')} GB
GPU: {snap.get('gpu_used_mb', '?')}/{snap.get('gpu_total_mb', '?')} MB (util: {snap.get('gpu_util_pct', '?')}%)
Swap: {snap.get('swap_used_gb', '?')}/{snap.get('swap_total_gb', '?')} GB
Docker: {snap.get('docker_containers', '?')}
Ollama Models: {snap.get('ollama_models', '?')}
Issues: {snap.get('issues', 'none')}
"""


# ── Session summaries → KB ────────────────────────────

def index_session_summaries(limit: int = 5) -> dict:
    """Index recently CLOSED session data into KB.

    Returns {indexed: int, errors: [str]}
    """
    result = {"indexed": 0, "errors": []}

    sessions = _guardian_query(
        "SELECT * FROM sessions WHERE status IN ('CLOSED','ZOMBIE') AND summary != '' ORDER BY closed_at DESC LIMIT ?",
        (limit,),
    )

    for s in sessions:
        sid = s.get("id", "unknown")[:12]
        text = f"""Claude Session: {sid}
Status: {s.get('status', '?')}
Started: {s.get('started_at', '?')}
Closed: {s.get('closed_at', '?')}
Tool calls: {s.get('tool_calls', 0)}
Tools used: {s.get('tool_names', '')}
Working directory: {s.get('cwd', '?')}
Summary: {s.get('summary', 'none')}
"""

        try:
            r = subprocess.run(
                [sys.executable or "python3", str(KB_ROOT / "scripts" / "kb_cli.py"),
                 "ingest", "--title", f"Session {sid}", "--tags", "session,auto-generated",
                 "--format", "text", "-"],
                input=text.encode("utf-8"),
                capture_output=True, text=True, timeout=30,
            )
            if "Ingested:" in r.stdout or "Already exists" in r.stdout:
                result["indexed"] += 1
        except Exception as e:
            result["errors"].append(str(e))

    return result


# ── System state query from KB ────────────────────────

def query_system_health_from_kb(query: str = "system health status") -> list[dict]:
    """Search KB for system health information."""
    try:
        r = subprocess.run(
            [sys.executable or "python3", str(KB_ROOT / "scripts" / "kb_cli.py"),
             "search", query, "--source", "memory", "--top-k", "3"],
            capture_output=True, text=True, timeout=30,
        )
        # Basic parse
        results = []
        for line in r.stdout.split("\n"):
            m = re.match(r"\s*\[([0-9.]+)\]\s+(.+?)\s+\((.+?)\)", line)
            if m:
                results.append({
                    "score": float(m.group(1)),
                    "title": m.group(2).strip(),
                    "format": m.group(3).strip(),
                })
        return results[:3]
    except Exception:
        return []


# ── Combined Guardian+KB health view ──────────────────

def get_guardian_kb_health() -> dict:
    """Combined health status from both Guardian and KB."""
    # Guardian stats
    sessions = _guardian_query("SELECT COUNT(*) as cnt FROM sessions")
    active = _guardian_query("SELECT COUNT(*) as cnt FROM sessions WHERE status IN ('ACTIVE','IDLE')")
    latest_health = _guardian_query("SELECT * FROM health_snapshots ORDER BY id DESC LIMIT 1")

    # KB stats
    kb_health = {"total_docs": 0, "total_chunks": 0, "total_vectors": 0}
    try:
        r = subprocess.run(
            [sys.executable or "python3", str(KB_ROOT / "scripts" / "kb_cli.py"), "status"],
            capture_output=True, text=True, timeout=10,
        )
        for line in r.stdout.split("\n"):
            if "Documents:" in line:
                kb_health["total_docs"] = int(re.search(r"(\d+)", line).group(1))
            elif "Chunks:" in line:
                kb_health["total_chunks"] = int(re.search(r"(\d+)", line).group(1))
            elif "Vectors:" in line:
                kb_health["total_vectors"] = int(re.search(r"(\d+)", line).group(1))
    except Exception:
        pass

    return {
        "guardian": {
            "total_sessions": sessions[0]["cnt"] if sessions else 0,
            "active_sessions": active[0]["cnt"] if active else 0,
            "latest_health": latest_health[0] if latest_health else {},
        },
        "kb": kb_health,
        "guardian_running": GUARDIAN_DB.exists(),
        "timestamp": _now(),
    }
