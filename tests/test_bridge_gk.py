"""Tests: Guardian ↔ KB bridge."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aegis.bridges.guardian_kb import (
    get_guardian_kb_health,
    query_system_health_from_kb,
)


def test_guardian_kb_health():
    health = get_guardian_kb_health()
    assert "guardian" in health
    assert "kb" in health
    assert "guardian_running" in health
    print(f"  [PASS] guardian+kb health (guardian_running={health['guardian_running']}, kb_docs={health['kb'].get('total_docs', 0)})")


def test_query_system_health():
    results = query_system_health_from_kb("health status")
    print(f"  [PASS] query system health from KB ({len(results)} results)")


def run():
    print("=== Bridge: Guardian ↔ KB ===")
    for test in [test_guardian_kb_health, test_query_system_health]:
        try:
            test()
        except Exception as e:
            print(f"  [FAIL] {e}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
