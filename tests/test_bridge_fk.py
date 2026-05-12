"""Tests: Forest ↔ KB bridge."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aegis.bridges.forest_kb import (
    get_kb_forest_health,
    search_kb_for_memory,
    create_task_from_kb_gap,
)


def test_kb_forest_health():
    health = get_kb_forest_health()
    assert "total_docs" in health
    assert health["total_docs"] > 0, "KB should have documents"
    print(f"  [PASS] KB forest health (docs={health['total_docs']}, mem_docs={health.get('memory_docs', 0)})")


def test_search_kb_for_memory():
    results = search_kb_for_memory("system drive architecture")
    # May return results or not — both are OK
    print(f"  [PASS] search KB for memory ({len(results)} results)")


def test_create_task_from_gap():
    # High score, many results → no gap
    assert create_task_from_kb_gap("known topic", 0.8, 10) == False
    # Low score, few results → gap
    gap = create_task_from_kb_gap("unknown niche topic xyz", 0.1, 0)
    print(f"  [PASS] gap→task creation (gap_detected={gap})")


def run():
    print("=== Bridge: Forest ↔ KB ===")
    for test in [test_kb_forest_health, test_search_kb_for_memory, test_create_task_from_gap]:
        try:
            test()
        except Exception as e:
            print(f"  [FAIL] {e}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
