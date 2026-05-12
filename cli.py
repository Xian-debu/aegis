#!/usr/bin/env python3
"""AEGIS CLI — unified command interface for the autonomous integration system.

Usage:
  aegis status               Full three-layer status dashboard
  aegis health               Health check with issues and warnings
  aegis sync                 Full sync across all bridges
  aegis search <query>       Search across KB and Forest
  aegis diagnose             Detect known issues + suggest fixes
  aegis fix <issue>          Apply a known fix (--dry-run to preview)

Alias: aegis = python3 /root/.claude/aegis/cli.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aegis.monitor import full_status, full_sync, health_check, search_all
from aegis.remediate import diagnose, apply_fix


def cmd_status():
    """Show full three-layer dashboard."""
    status = full_status()

    gf = status.get("layer_guardian", {})
    kb = status.get("layer_kb", {})
    integ = status.get("layer_integrated", {})

    print("╔══════════════════════════════════════════╗")
    print("║         AEGIS System Dashboard           ║")
    print("╠══════════════════════════════════════════╣")

    # Guardian layer
    print("║ L1: SYSTEM GUARDIAN                      ║")
    g = integ.get("guardian", {})
    print(f"║   Sessions: {g.get('active_sessions', 0)} active / {g.get('total_sessions', 0)} total")
    h = g.get("latest_health", {})
    if h:
        print(f"║   Health: disk={h.get('disk_pct','?')}% mem={h.get('mem_used_gb','?')}/{h.get('mem_total_gb','?')}GB gpu={h.get('gpu_used_mb','?')}/{h.get('gpu_total_mb','?')}MB")
        issues = h.get("issues", "")
        if issues:
            print(f"║   Issues: {issues}")

    # Forest layer
    print("║ L2: MEMORY FOREST                        ║")
    print(f"║   Active: {gf.get('forest_active', 0)}  Dormant: {gf.get('forest_dormant', 0)}  Running: {gf.get('forest_running', 0)}  Completed: {gf.get('forest_completed', 0)}")
    print(f"║   Zombie sessions: {gf.get('sessions_zombie', 0)}")

    # KB layer
    print("║ L3: KNOWLEDGE BASE                       ║")
    k = integ.get("kb", {})
    print(f"║   Docs: {k.get('total_docs', 0)}  Chunks: {k.get('total_chunks', 0)}  Vectors: {k.get('total_vectors', 0)}")
    kb_health = status.get("layer_kb", {})
    mem_docs = kb_health.get("memory_docs", 0)
    print(f"║   Memory-indexed: {mem_docs} docs ({kb_health.get('coverage_pct', 0)}%)")

    print("╚══════════════════════════════════════════╝")


def cmd_health():
    """Run health checks."""
    result = health_check()
    print(f"Health: {'OK' if result['healthy'] else 'ISSUES DETECTED'}")
    if result["issues"]:
        print("\nIssues:")
        for i in result["issues"]:
            print(f"  ❌ {i}")
    if result["warnings"]:
        print("\nWarnings:")
        for w in result["warnings"]:
            print(f"  ⚠️ {w}")
    if not result["issues"] and not result["warnings"]:
        print("  All systems nominal.")


def cmd_sync():
    """Run full bridge synchronization."""
    print("Syncing AEGIS bridges...")
    result = full_sync()
    gf = result["guardian_forest"]
    fk = result["forest_kb"]
    gk = result["guardian_kb"]
    print(f"  Guardian→Forest: synced={gf.get('synced',0)} zombied={gf.get('zombied',0)}")
    print(f"  Forest→KB: {fk.get('nodes_indexed',0)} indexed ({fk.get('errors',[])})")
    print(f"  Guardian→KB: health={gk['health_snapshots'].get('indexed',0)} sessions={gk['session_summaries'].get('indexed',0)}")
    print("Sync complete.")


def cmd_search(args: list[str]):
    """Search across KB and Forest."""
    query = " ".join(args)
    if not query.strip():
        print("Usage: aegis search <query>")
        return
    print(f"Searching: '{query}'...\n")
    results = search_all(query)
    kb_results = results.get("kb_results", [])
    if kb_results:
        for i, r in enumerate(kb_results[:5], 1):
            print(f"  [{r.get('score', 0):.3f}] {r.get('title', '?')} ({r.get('format', '?')})")
    else:
        print("  No results found in KB memory index.")


def cmd_diagnose():
    """Detect known issues and suggest fixes."""
    findings = diagnose()
    if not findings:
        print("No known issues detected.")
        return
    print(f"Found {len(findings)} issue(s):\n")
    for f in findings:
        icon = "🟢" if f["auto_applicable"] else "🟡"
        print(f"  {icon} [{f['risk'].upper()}] {f['description']}")
        print(f"     Fix: aegis fix {f['issue'].split(':')[0]}")
        print()


def cmd_fix(args: list[str]):
    """Apply a known fix."""
    dry_run = "--dry-run" in args
    issue = " ".join([a for a in args if not a.startswith("--")])
    if not issue:
        print("Usage: aegis fix <issue> [--dry-run]")
        print("Run 'aegis diagnose' to see known issues.")
        return

    print(f"Applying fix for: {issue} {'(dry run)' if dry_run else ''}")
    result = apply_fix(issue, dry_run=dry_run)
    if result.get("dry_run"):
        print(f"  Would run: {result.get('would_run', '?')}")
    elif result.get("applied"):
        print(f"  Applied: {result.get('command', '?')[:100]}")
        if result.get("stdout"):
            print(f"  Output: {result['stdout'][:200]}")
    else:
        print(f"  Failed: {result.get('error', 'unknown')}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "status": cmd_status,
        "health": cmd_health,
        "sync": cmd_sync,
        "search": lambda: cmd_search(args),
        "diagnose": cmd_diagnose,
        "fix": lambda: cmd_fix(args),
    }

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print(f"Available: {', '.join(sorted(commands.keys()))}")
        sys.exit(1)


if __name__ == "__main__":
    main()
