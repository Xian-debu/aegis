"""AEGIS Unified Monitor — single dashboard across all three layers."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aegis.bridges.guardian_forest import (
    get_session_forest_status, sync_sessions_to_forest,
    health_alert_to_forest,
)
from aegis.bridges.forest_kb import (
    index_forest_to_kb, get_kb_forest_health,
    search_kb_for_memory, create_task_from_kb_gap,
)
from aegis.bridges.guardian_kb import (
    index_health_snapshots, index_session_summaries,
    get_guardian_kb_health, query_system_health_from_kb,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def full_status() -> dict:
    """Complete AEGIS status across all three layers and bridges."""
    return {
        "timestamp": _now(),
        "layer_guardian": get_session_forest_status(),
        "layer_kb": get_kb_forest_health(),
        "layer_integrated": get_guardian_kb_health(),
    }


def full_sync() -> dict:
    """Run full synchronization across all bridges.

    Order: Guardian→Forest → Forest→KB → Guardian→KB
    Returns per-bridge results.
    """
    return {
        "guardian_forest": sync_sessions_to_forest(),
        "forest_kb": index_forest_to_kb(),
        "guardian_kb": {
            "health_snapshots": index_health_snapshots(5),
            "session_summaries": index_session_summaries(5),
        },
        "timestamp": _now(),
    }


def health_check() -> dict:
    """Run health checks across all layers, return issues."""
    issues = []
    warnings = []

    # Check Guardian
    from aegis.config import GUARDIAN_DB
    if not GUARDIAN_DB.exists():
        issues.append("guardian: database not found — daemon not running?")
    else:
        import sqlite3
        try:
            conn = sqlite3.connect(f"file:{GUARDIAN_DB}?mode=ro", uri=True)
            sessions = conn.execute("SELECT COUNT(*) FROM sessions WHERE status IN ('ACTIVE','IDLE')").fetchone()[0]
            zombies = conn.execute("SELECT COUNT(*) FROM sessions WHERE status='ZOMBIE'").fetchone()[0]
            if zombies > 0:
                warnings.append(f"guardian: {zombies} zombie session(s) detected")
            # Check last health snapshot age
            last = conn.execute("SELECT MAX(timestamp) FROM health_snapshots").fetchone()[0]
            if last:
                from datetime import timedelta
                try:
                    last_dt = datetime.fromisoformat(last)
                    if (datetime.now(timezone.utc) - last_dt) > timedelta(hours=2):
                        warnings.append(f"guardian: last health snapshot {last_dt.strftime('%H:%M')} (>2h ago)")
                except Exception:
                    pass
            conn.close()
        except Exception as e:
            issues.append(f"guardian: DB error: {e}")

    # Check Memory Forest
    from aegis.config import MEMORY_ROOT
    if not MEMORY_ROOT.exists():
        issues.append("forest: memory root not found")
    else:
        md_count = len(list(MEMORY_ROOT.rglob("*.md")))
        if md_count < 50:
            warnings.append(f"forest: only {md_count} nodes (possible corruption)")

    # Check KB
    from aegis.config import KB_ROOT
    kb_db = KB_ROOT / "data" / "kb.sqlite"
    kb_idx = KB_ROOT / "data" / "vector_index.pkl"
    if not kb_db.exists():
        issues.append("kb: SQLite database missing")
    if not kb_idx.exists():
        issues.append("kb: vector index missing")

    return {
        "healthy": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "timestamp": _now(),
    }


def search_all(query: str) -> dict:
    """Search across KB and Forest for a query."""
    kb_results = search_kb_for_memory(query, 5)
    return {
        "query": query,
        "kb_results": kb_results,
        "timestamp": _now(),
    }
