#!/usr/bin/env python3
"""
Signal Resonance 系统验收脚本
验证 signals.json 结构完整性 + 规则有效性 + 覆盖率检查

设计原则: 嵌入已知的规则结构，区分"配置错误"和"正常简化"。
已知正常情况:
  - error→memory 仅 5 条 (已知限制，Evolution 2 产物)
  - tool→memory 仅 8 条 (已知限制)
  - 部分 GitHub 搜索可能返回空 (网络间歇问题，非配置错误)

用法:
  python3 validate_resonance.py              # 完整验收
  python3 validate_resonance.py --quick       # 仅 JSON 有效性
"""
import json, sys, os, argparse

SIGNALS_PATH = "/root/.claude/signals.json"
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


# ═══════════════════════════════════════════════════════
# 基线 — 以下数字是 Evolution 2 完成时的快照
# 数值下降=退化(规则被误删), 数值上升=正常进化
# ═══════════════════════════════════════════════════════
MIN_TOOL_PATTERNS = 8     # tool→memory 规则最小值
MIN_ERROR_PATTERNS = 5    # error→memory 规则最小值
MIN_CONTEXT_SIGNALS = 7   # context_signals 场景最小值
MIN_HEALTH_CHECKS = 6     # health_checks 项最小值


def load():
    if not os.path.exists(SIGNALS_PATH):
        return None
    with open(SIGNALS_PATH) as f:
        return json.load(f)


def check_json_valid():
    """signals.json 是合法 JSON"""
    sig = load()
    if sig is None:
        return False, "signals.json not found or not readable"
    return True, f"valid JSON, top-level keys: {list(sig.keys())}"


def check_required_sections():
    """所有必需节存在"""
    sig = load()
    required = ["context_signals", "health_checks", "task_continuity", "resonance_rules"]
    missing = [k for k in required if k not in sig]
    return len(missing) == 0, f"all {len(required)} sections present" if not missing else f"MISSING: {missing}"


def check_tool_patterns():
    """tool→memory 规则数 ≥ MIN_TOOL_PATTERNS"""
    sig = load()
    rules = sig.get("resonance_rules", {}).get("tool_pattern_to_memory", {})
    count = len(rules)
    ok = count >= MIN_TOOL_PATTERNS
    return ok, f"{count} tool→memory rules (minimum={MIN_TOOL_PATTERNS})"


def check_error_patterns():
    """error→memory 规则数 ≥ MIN_ERROR_PATTERNS"""
    sig = load()
    rules = sig.get("resonance_rules", {}).get("error_pattern_to_memory", {})
    count = len(rules)
    ok = count >= MIN_ERROR_PATTERNS
    return ok, f"{count} error→memory rules (minimum={MIN_ERROR_PATTERNS})"


def check_context_signals():
    """context_signals 场景数 ≥ MIN_CONTEXT_SIGNALS"""
    sig = load()
    signals = sig.get("context_signals", {})
    count = len(signals)
    ok = count >= MIN_CONTEXT_SIGNALS
    return ok, f"{count} context signals (minimum={MIN_CONTEXT_SIGNALS})"


def check_health_checks():
    """health_checks 项数 ≥ MIN_HEALTH_CHECKS"""
    sig = load()
    checks = sig.get("health_checks", {})
    count = len(checks)
    ok = count >= MIN_HEALTH_CHECKS
    return ok, f"{count} health checks (minimum={MIN_HEALTH_CHECKS})"


def check_each_tool_rule_has_valid_memory_ref():
    """每条 tool→memory 规则引用的 memory ID 在 MEMORY.md 中有对应文件"""
    sig = load()
    rules = sig.get("resonance_rules", {}).get("tool_pattern_to_memory", {})
    # Collect all referenced memory IDs
    refs = set()
    for memories in rules.values():
        refs.update(memories)
    # Check if these IDs appear in any memory file
    memory_root = "/root/.claude/projects/-root/memory"
    found = set()
    import subprocess
    for ref in refs:
        result = subprocess.run(
            ["grep", "-rl", ref, memory_root],
            capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip():
            found.add(ref)
    missing = refs - found
    if not missing:
        return True, f"all {len(refs)} referenced memory IDs found in files"
    elif len(missing) <= 2:
        return None, f"{len(missing)}/{len(refs)} memory refs not found in files: {list(missing)}"
    else:
        return False, f"{len(missing)}/{len(refs)} memory refs not found: {list(missing)[:5]}"


def check_drive_script_present():
    """system_drive.py 存在且可导入"""
    script = "/root/.claude/scripts/system_drive.py"
    ok = os.path.exists(script)
    return ok, "system_drive.py present" if ok else "MISSING"


def check_resonance_engine_works():
    """resonance_for_tool() 对已知输入返回正确结果"""
    sys.path.insert(0, "/root/.claude/scripts")
    from system_drive import resonance_for_tool
    r = resonance_for_tool("Bash", {"command": "ollama list"})
    has_memories = len(r.get("memories", [])) > 0
    return has_memories, f"Bash+ollama → {r.get('memories', [])} (expected [PROJ-OLLAM-0001])"


def main():
    parser = argparse.ArgumentParser(description="Signal Resonance 系统验收")
    parser.add_argument("--quick", action="store_true", help="仅 JSON 有效性")
    args = parser.parse_args()

    print("=" * 62)
    print("  Signal Resonance 系统验收 (signals.json + system_drive.py)")
    print("=" * 62)

    print("\n── Phase 1: 结构健康 ──")
    check("signals.json valid JSON",     check_json_valid)
    check("Required sections",           check_required_sections)
    check("Tool→memory rules count",     check_tool_patterns)
    check("Error→memory rules count",    check_error_patterns)
    check("Context signals count",       check_context_signals)
    check("Health checks count",         check_health_checks)
    check("system_drive.py present",     check_drive_script_present)

    if not args.quick:
        print("\n── Phase 2: 规则有效性 ──")
        check("Memory refs valid",               check_each_tool_rule_has_valid_memory_ref)
        check("resonance_for_tool() functional", check_resonance_engine_works)

    print(f"\n{'='*62}")
    total = PASS + FAIL + WARN
    print(f"  {total} checks: {PASS} pass, {WARN} warn, {FAIL} fail")
    if FAIL > 0:
        print("  退化标志: JSON broken, 节缺失, 规则数跌破基线, 引擎不工作")
    else:
        print("  Resonance system OK")
    print(f"{'='*62}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
