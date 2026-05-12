#!/usr/bin/env python3
"""AEGIS full integration tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aegis.monitor import full_status, full_sync, health_check
from aegis.remediate import diagnose


def test_full_status():
    status = full_status()
    assert "timestamp" in status
    assert "layer_guardian" in status
    assert "layer_kb" in status
    assert "layer_integrated" in status
    print(f"  [PASS] full status (3 layers present)")


def test_health_check():
    result = health_check()
    assert "healthy" in result
    assert "issues" in result
    assert "warnings" in result
    print(f"  [PASS] health check (healthy={result['healthy']}, issues={len(result['issues'])}, warnings={len(result['warnings'])})")


def test_diagnose():
    findings = diagnose()
    assert isinstance(findings, list)
    print(f"  [PASS] diagnose ({len(findings)} findings)")
    for f in findings:
        print(f"    - [{f['risk']}] {f['description']}")


def run():
    tests = [
        ("Full Status Dashboard", test_full_status),
        ("Health Check", test_health_check),
        ("Issue Diagnosis", test_diagnose),
    ]
    passed = 0
    failed = 0
    print("=" * 50)
    print("AEGIS Integration Tests")
    print("=" * 50)
    for name, test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1
    print(f"\nResults: {passed} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    sys.exit(run())
