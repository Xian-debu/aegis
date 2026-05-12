"""Tests: Guardian ↔ Forest bridge."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aegis.bridges.guardian_forest import (
    sync_sessions_to_forest,
    health_alert_to_forest,
    get_session_forest_status,
    _cwd_to_project,
    _mark_zombie_nodes_dormant,
)


def test_cwd_to_project():
    # Without custom PROJECT_PATH_MAP, falls back to directory name
    result = _cwd_to_project("/home/user/my-project")
    assert result == "my-project"
    result2 = _cwd_to_project("/some/unknown/path")
    assert result2 == "path"
    print("  [PASS] cwd→project mapping (uses directory name fallback)")


def test_health_alert_to_forest():
    result = health_alert_to_forest(["disk:85%", "memory:92%"])
    assert "created" in result
    assert "updated" in result
    assert result["created"] + result["updated"] == 2
    print(f"  [PASS] health alert → forest (created={result['created']}, updated={result['updated']})")


def test_session_forest_status():
    status = get_session_forest_status()
    assert "sessions_active" in status
    assert "forest_active" in status
    assert "forest_dormant" in status
    assert "timestamp" in status
    print(f"  [PASS] session+forest status (active={status['sessions_active']}, forest_active={status['forest_active']})")


def run():
    print("=== Bridge: Guardian ↔ Forest ===")
    for test in [test_cwd_to_project, test_health_alert_to_forest, test_session_forest_status]:
        try:
            test()
        except Exception as e:
            print(f"  [FAIL] {e}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
