#!/usr/bin/env python3
"""mf — Memory Forest CLI tool for quick memory operations.

Usage:
  mf status                        Forest status report
  mf heartbeat [--dry-run]         Heartbeat all active nodes
  mf heartbeat <node-id>           Heartbeat specific node
  mf gc [-n|--dry-run]             Garbage collection candidates
  mf gc --execute                  Execute GC (with confirmation)
  mf search <query>                Full-text search
  mf health                        Forest health check
  mf create <tree> <type> <title> [--parent <id>] [--layer L1-L4]
  mf list [tree]                   List nodes in a tree (or all)
  mf show <node-id>                Display a node
  mf drive                         System drive status (health + tasks + context)
  mf d                             Alias for drive
"""

import sys
import os

# Ensure the scripts directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memory_forest import (
    MEMORY_ROOT, heartbeat_all, heartbeat_node, gc_check, gc_run,
    forest_status, status_report, search_nodes, create_node,
    forest_health, collect_all_nodes, node_by_id, _today
)


def cmd_status(args):
    print(status_report())


def cmd_heartbeat(args):
    dry = "--dry-run" in args or "-n" in args
    # Check if a specific node ID is given
    specific = None
    for a in args:
        if not a.startswith("-") and a != "heartbeat":
            specific = a
            break

    if specific:
        node = node_by_id(specific)
        if not node:
            print(f"Error: node '{specific}' not found")
            sys.exit(1)
        changes = heartbeat_node(node, dry_run=dry)
        if changes:
            print("\n".join(changes))
        else:
            print(f"Node {specific}: heartbeat already up to date.")
        return

    changes = heartbeat_all(dry_run=dry)
    if changes:
        prefix = "[DRY RUN] " if dry else ""
        print(f"{prefix}Heartbeat: {len(changes)} changes")
        for c in changes:
            print(c)
    else:
        print("No heartbeat changes needed.")


def cmd_gc(args):
    dry = "-n" in args or "--dry-run" in args
    execute = "--execute" in args

    if execute:
        print("This will modify memory files. Dry run first:")
        eligible = gc_check()
        if not eligible:
            print("  No GC candidates found.")
            return
        for e in eligible:
            print(f"  {e['node']['frontmatter'].get('id')}: {e['reason']}")
        resp = input("\nProceed with GC? [y/N] ")
        if resp.lower() == "y":
            actions = gc_run(dry_run=False)
            print("\n".join(actions))
        else:
            print("Aborted.")
        return

    eligible = gc_check()
    if not eligible:
        print("No GC candidates found.")
        return

    print(f"GC candidates: {len(eligible)}")
    for e in eligible:
        n = e["node"]
        fm = n["frontmatter"]
        print(f"  {fm.get('id')} ({fm.get('status')}, L{fm.get('layer', '?')}): {e['reason']}")
    print("\nRun 'mf gc --execute' to perform GC with confirmation.")


def cmd_search(args):
    query = " ".join(args)
    results = search_nodes(query)
    if not results:
        print(f"No results for: {query}")
        return
    print(f"Results for '{query}': {len(results)} found")
    for r in results:
        print(f"  [{r['score']}] {r['id']} | {r['title'][:60]} | {r['status']} | {r['heartbeat']}")


def cmd_health(args):
    h = forest_health()
    status = "HEALTHY" if h["healthy"] else "UNHEALTHY"
    print(f"Forest health: {status}")
    print(f"  Total nodes: {h['total_nodes']}")
    if h["issues"]:
        print(f"  Issues ({len(h['issues'])}):")
        for i in h["issues"]:
            print(f"    - {i}")
    if h["warnings"]:
        print(f"  Warnings ({len(h['warnings'])}):")
        for w in h["warnings"]:
            print(f"    - {w}")


def cmd_create(args):
    try:
        tree = args[0]
        ntype = args[1].upper()
        title = " ".join(args[2:]).split(" --")[0]  # stop at first --

        parent = None
        layer = "L1"
        for i, a in enumerate(args):
            if a == "--parent" and i + 1 < len(args):
                parent = args[i + 1]
            if a == "--layer" and i + 1 < len(args):
                layer = args[i + 1]

        node = create_node(tree=tree, node_type=ntype, title=title,
                          parent_id=parent, layer=layer)
        print(f"Created: {node['id']}")
        print(f"  File: {node['filepath']}")
    except (IndexError, ValueError) as e:
        print(f"Usage: mf create <tree> <TYPE> <title> [--parent <id>] [--layer L1-L4]")
        print(f"  tree: forest | system | experiences | projects | <custom>")
        print(f"  TYPE: ROOT | BRANCH | LEAF | EXPERIENCE")
        sys.exit(1)


def cmd_list(args):
    nodes = collect_all_nodes()
    tree_filter = args[0] if args else None

    for n in sorted(nodes, key=lambda x: (x["frontmatter"].get("tree", ""), x["frontmatter"].get("type", ""), x["frontmatter"].get("id", ""))):
        fm = n["frontmatter"]
        t = fm.get("tree", "?")
        if tree_filter and t != tree_filter:
            continue
        title = n["body"].split("\n")[0].lstrip("# ")[:60]
        print(f"  [{t}] {fm.get('id'):20s} {fm.get('type', '?'):10s} {fm.get('status', '?'):10s} {title}")


def cmd_show(args):
    nid = args[0]
    node = node_by_id(nid)
    if not node:
        print(f"Node '{nid}' not found.")
        sys.exit(1)

    fm = node["frontmatter"]
    body = node["body"]

    print(f"=== {nid} ===")
    print(f"File: {node['filepath']}")
    print(f"Type: {fm.get('type')}  Tree: {fm.get('tree')}  Layer: {fm.get('layer')}")
    print(f"Status: {fm.get('status')}  Priority: {fm.get('priority')}")
    print(f"Created: {fm.get('created')}  Heartbeat: {fm.get('heartbeat')}")
    print(f"Parent: {fm.get('parent')}  Children: {fm.get('children')}")
    if fm.get("tags"):
        print(f"Tags: {', '.join(fm['tags'])}")
    print(f"\n{body[:2000]}")
    if len(body) > 2000:
        print(f"\n... ({len(body) - 2000} more chars)")


def _cmd_drive(args):
    """mf drive — show system drive status."""
    try:
        from system_drive import cmd_status as drive_status
        drive_status()
    except ImportError:
        print("System drive engine not available (system_drive.py not found)")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "status": cmd_status,
        "heartbeat": cmd_heartbeat,
        "gc": cmd_gc,
        "search": cmd_search,
        "health": cmd_health,
        "create": cmd_create,
        "list": cmd_list,
        "show": cmd_show,
        "ls": cmd_list,
        "drive": lambda args: _cmd_drive(args),
        "d": lambda args: _cmd_drive(args),
    }

    if cmd in commands:
        commands[cmd](args)
    else:
        print(f"Unknown command: {cmd}")
        print(f"Available: {', '.join(sorted(commands.keys()))}")
        sys.exit(1)


if __name__ == "__main__":
    main()
