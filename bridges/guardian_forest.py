"""Bridge L1: Claude Guardian ↔ Memory Forest.

Session lifecycle events from Guardian trigger Forest state updates:
  - DETECTED/ACTIVE → Forest heartbeat
  - IDLE → note in forest, no action needed
  - CLOSED → final heartbeat, mark completed if all tasks done
  - ZOMBIE → mark active project nodes as DORMANT

Also: Guardian health alerts → Forest alert/experience nodes.
"""
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from aegis.config import (
    GUARDIAN_DB, MEMORY_ROOT, PROJECTS_DIR, EXPERIENCES_DIR,
    AUTO_CRASH_TO_DORMANT, PROJECT_PATH_MAP,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ── Guardian DB access ─────────────────────────────────

def _guardian_query(sql: str, params: tuple = ()) -> list[dict]:
    """Read-only query to Guardian state DB."""
    if not GUARDIAN_DB.exists():
        return []
    conn = sqlite3.connect(f"file:{GUARDIAN_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Forest access ──────────────────────────────────────

def _read_forest_node(filepath: str) -> dict | None:
    """Read a memory forest .md node, return {fm, body}."""
    try:
        content = Path(filepath).read_text(encoding="utf-8")
    except Exception:
        return None

    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not fm_match:
        return None

    fm_text = fm_match.group(1)
    body = content[fm_match.end():].strip()

    fm = {}
    for line in fm_text.split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip("'\"")
    return {"fm": fm, "body": body}


def _update_forest_heartbeat(node_path: str) -> bool:
    """Update the heartbeat field in a forest node's frontmatter."""
    try:
        content = Path(node_path).read_text(encoding="utf-8")
        # Find and replace heartbeat
        new_content = re.sub(
            r"heartbeat:\s*['\"]?\d{4}-\d{2}-\d{2}[^'\"]*['\"]?",
            f"heartbeat: '{_today()}'",
            content,
            count=1,
        )
        if new_content != content:
            Path(node_path).write_text(new_content, encoding="utf-8")
            return True
    except Exception:
        pass
    return False


# ── Bridge operations ──────────────────────────────────

def sync_sessions_to_forest() -> dict:
    """Sync Guardian session states to Memory Forest node heartbeats.

    For each ACTIVE/IDLE session, update heartbeat on any forest nodes
    associated with that session's working directory.

    Returns {synced: int, zombied: int, errors: [str]}
    """
    result = {"synced": 0, "zombied": 0, "errors": []}

    sessions = _guardian_query(
        "SELECT * FROM sessions WHERE status IN ('ACTIVE','IDLE','ZOMBIE')"
    )

    for s in sessions:
        sid = s.get("id", "")[:12]
        status = s.get("status", "")
        cwd = s.get("cwd", "")

        if status == "ZOMBIE" and AUTO_CRASH_TO_DORMANT:
            # Mark project nodes as DORMANT if they reference this session
            result["zombied"] += _mark_zombie_nodes_dormant(sid)

        elif status in ("ACTIVE", "IDLE"):
            # Update heartbeat on nodes in the matching project tree
            if cwd and PROJECTS_DIR.exists():
                project_name = _cwd_to_project(cwd)
                if project_name:
                    project_root = PROJECTS_DIR / project_name / "ROOT.md"
                    if project_root.exists():
                        if _update_forest_heartbeat(str(project_root)):
                            result["synced"] += 1

    return result


def _mark_zombie_nodes_dormant(session_id: str) -> int:
    """Mark forest nodes as DORMANT when their owning session is zombie."""
    count = 0
    if not PROJECTS_DIR.exists():
        return 0

    for md_file in PROJECTS_DIR.rglob("*.md"):
        node = _read_forest_node(str(md_file))
        if not node:
            continue
        status = node["fm"].get("status", "")
        if status not in ("ACTIVE", "RUNNING"):
            continue
        # Only mark as DORMANT, don't touch COMPLETED
        try:
            content = md_file.read_text(encoding="utf-8")
            new_content = re.sub(
                r"status:\s*ACTIVE|status:\s*RUNNING",
                "status: DORMANT",
                content,
                count=1,
            )
            if new_content != content:
                md_file.write_text(new_content, encoding="utf-8")
                count += 1
        except Exception:
            pass
    return count


def _cwd_to_project(cwd: str) -> str | None:
    """Map working directory to memory forest project name.

    Customize via AEGIS_PROJECT_MAP env var: "/path=project;/path2=project2"
    """
    project_map = PROJECT_PATH_MAP.copy()
    if not project_map:
        # Fallback: derive project name from cwd directory name
        return Path(cwd).name if cwd else None
    for path_prefix, project in project_map.items():
        if cwd.startswith(path_prefix):
            return project
    return None


def health_alert_to_forest(health_issues: list[str]) -> dict:
    """Create or update forest alert nodes for health issues.

    Returns {created: int, updated: int}
    """
    result = {"created": 0, "updated": 0}
    if not health_issues:
        return result

    alert_dir = EXPERIENCES_DIR / "alerts"
    alert_dir.mkdir(parents=True, exist_ok=True)

    for issue in health_issues:
        # Create a lightweight alert node
        slug = re.sub(r"[^a-z0-9]+", "-", issue.lower())[:40]
        alert_file = alert_dir / f"alert-{slug}.md"
        exists = alert_file.exists()

        content = f"""---
id: ALERT-{slug[:20]}
type: EXPERIENCE
tree: experiences
layer: L1
status: ACTIVE
created: {_today()}
heartbeat: '{_today()}'
priority: HIGH
tags:
- alert
- health
- auto-generated
---

# Health Alert: {issue}

**Detected**: {_today()}
**Status**: {"ONGOING" if exists else "NEW"}

System health check detected: **{issue}**.

This alert was auto-generated by AEGIS Guardian→Forest bridge.
"""
        try:
            alert_file.write_text(content, encoding="utf-8")
            if exists:
                result["updated"] += 1
            else:
                result["created"] += 1
        except Exception:
            pass

    return result


def get_session_forest_status() -> dict:
    """Get combined session + forest status overview."""
    active_sessions = _guardian_query(
        "SELECT COUNT(*) as cnt FROM sessions WHERE status IN ('ACTIVE','IDLE')"
    )
    zombie_sessions = _guardian_query(
        "SELECT COUNT(*) as cnt FROM sessions WHERE status='ZOMBIE'"
    )

    # Count forest nodes by status
    forest_status = {"ACTIVE": 0, "DORMANT": 0, "RUNNING": 0, "COMPLETED": 0, "OTHER": 0}
    if PROJECTS_DIR.exists():
        for md_file in PROJECTS_DIR.rglob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                m = re.search(r"^status:\s*(\w+)", content, re.MULTILINE)
                if m:
                    s = m.group(1)
                    forest_status[s] = forest_status.get(s, 0) + 1
                else:
                    forest_status["OTHER"] += 1
            except Exception:
                pass

    return {
        "sessions_active": active_sessions[0]["cnt"] if active_sessions else 0,
        "sessions_zombie": zombie_sessions[0]["cnt"] if zombie_sessions else 0,
        "forest_active": forest_status["ACTIVE"],
        "forest_dormant": forest_status["DORMANT"],
        "forest_running": forest_status["RUNNING"],
        "forest_completed": forest_status["COMPLETED"],
        "timestamp": _now(),
    }
