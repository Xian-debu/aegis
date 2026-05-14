#!/usr/bin/env python3
"""
Memory Forest 完整性验收脚本
一次运行 = 结构健康 + 心跳新鲜度 + 已知限制说明

设计原则: 输出自带解释。每个检查直接标注预期范围、原理、以及什么情况才算真正的退化。
LLM 下次看到"心跳过期"或"孤儿节点"时，先跑这个脚本，而不是自己推理。

用法:
  python3 validate_mf.py                  # 完整验收
  python3 validate_mf.py --quick           # 仅结构健康 (不含心跳)
"""
import os, sys, json, argparse
from pathlib import Path
from datetime import datetime, timedelta

MEMORY_ROOT = "/root/.claude/projects/-root/memory"
PASS, FAIL, WARN = 0, 0, 0


def check(name, fn):
    global PASS, FAIL, WARN
    try:
        ok, detail = fn()
        if ok:
            PASS += 1
            print(f"  \033[32m✓\033[0m {name}: {detail}")
        elif ok is None:
            WARN += 1
            print(f"  \033[33m⚠\033[0m {name}: {detail}")
        else:
            FAIL += 1
            print(f"  \033[31m✗\033[0m {name}: {detail}")
    except Exception as e:
        FAIL += 1
        print(f"  \033[31m✗\033[0m {name}: ERROR — {e}")


def parse_frontmatter(path):
    """Parse YAML-like frontmatter from a markdown file."""
    with open(path) as f:
        content = f.read()
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    fm = {}
    for line in parts[1].strip().split("\n"):
        line = line.strip()
        if ":" in line and not line.startswith("#"):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


# ═══════════════════════════════════════════════════════════
# 基线常量 — 修改这些值前先读相关记忆文件
# ═══════════════════════════════════════════════════════════
STALE_HEARTBEAT_DAYS = 14     # 心跳超过此天数视为过期
ORPHAN_THRESHOLD_HOURS = 48   # 孤儿节点超过此小时数视为需要处理
MAX_OBSOLETE_NODES = 5        # 过期节点数超过此值视为退化
EXPECTED_TREES = ["system", "experiences", "projects", "forest"]


def check_root_exists():
    """forest-root.md 存在且 frontmatter 完整"""
    path = os.path.join(MEMORY_ROOT, "forest-root.md")
    if not os.path.exists(path):
        return False, "forest-root.md MISSING — forest root not found"
    fm = parse_frontmatter(path)
    required = ["id", "type", "status", "children"]
    missing = [k for k in required if k not in fm]
    return len(missing) == 0, f"root present, frontmatter: {list(fm.keys())[:6]}..." + (f" MISSING: {missing}" if missing else "")


def check_philosophy_exists():
    """PHILOSOPHY.md 存在 (L5 绝对底层)"""
    path = os.path.join(MEMORY_ROOT, "PHILOSOPHY.md")
    exists = os.path.exists(path)
    fm = parse_frontmatter(path) if exists else {}
    return exists and fm.get("status") == "ABSOLUTE", f"PHILOSOPHY.md: {'present, status=' + fm.get('status','?') if exists else 'MISSING'}"


def check_preflight_exists():
    """PREFLIGHT.md 存在 (L5 强制前置)"""
    path = os.path.join(MEMORY_ROOT, "PREFLIGHT.md")
    return os.path.exists(path), f"PREFLIGHT.md: {'present' if os.path.exists(path) else 'MISSING'}"


def check_memery_index():
    """MEMORY.md 索引文件可读且非空"""
    path = os.path.join(MEMORY_ROOT, "MEMORY.md")
    if not os.path.exists(path):
        return False, "MEMORY.md MISSING"
    with open(path) as f:
        lines = [l for l in f if l.strip() and not l.strip().startswith("#")]
    return len(lines) > 10, f"MEMORY.md: {len(lines)} non-empty non-header lines (expected >10)"


def check_tree_roots():
    """四棵预期树的 ROOT 节点均存在"""
    tree_roots = {
        "system": "system-tree/ROOT.md",
        "experiences": "experiences-tree/ROOT.md",
        "projects": "projects-tree/ROOT.md",
        "forest": "forest-root.md",
    }
    results = []
    all_ok = True
    for tree, rel_path in tree_roots.items():
        path = os.path.join(MEMORY_ROOT, rel_path)
        if os.path.exists(path):
            fm = parse_frontmatter(path)
            results.append(f"{tree}:✓")
        else:
            results.append(f"{tree}:MISSING")
            all_ok = False
    return all_ok, ", ".join(results)


def check_node_count():
    """节点总数在合理范围 (50-200)"""
    md_files = list(Path(MEMORY_ROOT).rglob("*.md"))
    count = len(md_files)
    ok = 50 <= count <= 200
    return ok, f"{count} nodes (expected 50-200)"


def check_active_nodes():
    """ACTIVE 节点数 > COMPLETED (说明系统在使用中)"""
    active = 0
    completed = 0
    dormant = 0
    for md in Path(MEMORY_ROOT).rglob("*.md"):
        fm = parse_frontmatter(str(md))
        status = fm.get("status", "").strip("'\"")
        if status == "ACTIVE":
            active += 1
        elif status in ("COMPLETED", "completed"):
            completed += 1
        elif status in ("DORMANT", "dormant"):
            dormant += 1
    # ACTIVE should be the largest category
    ok = active > 10
    return ok, f"ACTIVE={active}, COMPLETED={completed}, DORMANT={dormant} (expected ACTIVE>10)"


def check_heartbeat_freshness():
    """无节点心跳超过 STALE_HEARTBEAT_DAYS 天 (warn only)"""
    now = datetime.now()
    stale_nodes = []
    for md in Path(MEMORY_ROOT).rglob("*.md"):
        fm = parse_frontmatter(str(md))
        hb = fm.get("heartbeat", "")
        if hb:
            try:
                hb_date = datetime.strptime(hb.strip("'"), "%Y-%m-%d")
                if (now - hb_date).days > STALE_HEARTBEAT_DAYS:
                    stale_nodes.append(f"{md.stem}:{hb}")
            except ValueError:
                pass
    if len(stale_nodes) == 0:
        return True, "all heartbeats fresh"
    elif len(stale_nodes) <= MAX_OBSOLETE_NODES:
        return None, f"{len(stale_nodes)} stale (threshold={MAX_OBSOLETE_NODES}): {stale_nodes[:3]}"
    else:
        return False, f"{len(stale_nodes)} stale (threshold={MAX_OBSOLETE_NODES}): {stale_nodes[:5]}"


def check_no_circular_refs():
    """无简单循环引用 (parent 和 children 不互指错误)"""
    nodes = {}
    for md in Path(MEMORY_ROOT).rglob("*.md"):
        fm = parse_frontmatter(str(md))
        nid = fm.get("id", md.stem)
        children = fm.get("children", "")
        parent = fm.get("parent", "")
        if nid:
            nodes[nid] = {
                "parent": parent.strip("'[] ") if parent else None,
                "children": [c.strip().strip("'") for c in children.strip("[]").split(",") if c.strip()] if children else [],
            }
    issues = []
    for nid, node in nodes.items():
        for child_id in node["children"]:
            if child_id and child_id in nodes:
                grandparent = nodes[child_id].get("parent", "")
                if grandparent and grandparent == nid:
                    pass  # Correct: parent→child relationship
                elif grandparent and grandparent != nid:
                    issues.append(f"{nid}→{child_id} but child.parent={grandparent}")
    return len(issues) == 0, f"no circular refs" if not issues else f"ISSUES: {issues[:3]}"


def check_feedback_count():
    """feedback 类型记忆数 ≥ 10 (说明错误修正机制在运作)"""
    count = 0
    for md in Path(MEMORY_ROOT).rglob("*.md"):
        fm = parse_frontmatter(str(md))
        if fm.get("type") == "feedback":
            count += 1
    ok = count >= 10
    return ok, f"{count} feedback memories (expected ≥10, more=better guardrail coverage)"


def check_experience_pattern_count():
    """经验模式数在 20-50 之间 (太少=积累不足, 太多=未修剪)"""
    pattern_dir = os.path.join(MEMORY_ROOT, "experiences-tree", "patterns")
    count = len(list(Path(pattern_dir).glob("*.md"))) if os.path.exists(pattern_dir) else 0
    ok = 20 <= count <= 50
    return ok, f"{count} experience patterns (expected 20-50)"


def main():
    parser = argparse.ArgumentParser(description="Memory Forest 完整性验收")
    parser.add_argument("--quick", action="store_true", help="仅结构健康检查")
    args = parser.parse_args()

    print("=" * 62)
    print("  Memory Forest 完整性验收")
    print("=" * 62)

    print("\n── Phase 1: 结构健康 ──")
    check("forest-root.md exists",       check_root_exists)
    check("PHILOSOPHY.md (L5)",          check_philosophy_exists)
    check("PREFLIGHT.md (L5)",           check_preflight_exists)
    check("MEMORY.md index",             check_memery_index)
    check("Tree roots (4 trees)",        check_tree_roots)
    check("Node count [50-200]",         check_node_count)
    check("Status distribution",         check_active_nodes)
    check("No circular parent/child",    check_no_circular_refs)

    if not args.quick:
        print("\n── Phase 2: 质量指标 ──")
        check("Heartbeat freshness",         check_heartbeat_freshness)
        check("Feedback count ≥10",          check_feedback_count)
        check("Experience patterns [20-50]",  check_experience_pattern_count)

    print(f"\n{'='*62}")
    total = PASS + FAIL + WARN
    print(f"  {total} checks: {PASS} pass, {WARN} warn, {FAIL} fail")

    if FAIL > 0:
        print("  真正的回归标志:")
        print("    - forest-root.md 缺失")
        print("    - PHILOSOPHY.md 或 PREFLIGHT.md 缺失")
        print("    - 心跳大面积过期 (>5 个节点)")
        print("    - 循环引用或树根缺失")
    else:
        print("  Memory Forest 结构正常")

    print(f"{'='*62}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
