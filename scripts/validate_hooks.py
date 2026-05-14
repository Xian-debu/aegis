#!/usr/bin/env python3
"""
Hooks 配置完整性验收脚本
验证 settings.json + settings.local.json 的结构 + hook 脚本存在性

设计原则: 嵌入已知的 hook 配置结构。区分"有意简化"和"配置错误"。
已知正常情况:
  - settings.json 只有 3 个顶层 hook (WebSearch/WebFetch block)
  - settings.local.json 有 SessionStart + Stop + 2x PreToolUse
  - PreToolUse system_drive.py 的 stderr 输出不会注入 LLM 上下文 (已知限制)

用法:
  python3 validate_hooks.py                  # 完整验收
  python3 validate_hooks.py --quick           # 仅 JSON 有效性
"""
import json, os, sys, argparse

SETTINGS = "/root/.claude/settings.json"
SETTINGS_LOCAL = "/root/.claude/settings.local.json"
SCRIPTS_DIR = "/root/.claude/scripts"
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
# 基线 — Evolution 2 完成时的 hook 结构
# 这些数字/名称是"正常"的基准，变化需有意识
# ═══════════════════════════════════════════════════════
REQUIRED_HOOK_TYPES = ["SessionStart", "Stop", "PreToolUse"]
REQUIRED_HOOK_SCRIPTS = [
    "startup_hook.py",
    "heartbeat_hook.py",
    "system_drive.py",
]
EXPECTED_PRETOOLUSE_COUNT = 2  # Number of PreToolUse entries in local settings


def check_settings_json():
    """settings.json 是合法 JSON"""
    if not os.path.exists(SETTINGS):
        return False, "settings.json MISSING"
    with open(SETTINGS) as f:
        data = json.load(f)
    hooks = data.get("hooks", {})
    hook_count = len(hooks)
    return True, f"valid JSON, {hook_count} hook types"


def check_settings_local_json():
    """settings.local.json 是合法 JSON"""
    if not os.path.exists(SETTINGS_LOCAL):
        return False, "settings.local.json MISSING"
    with open(SETTINGS_LOCAL) as f:
        data = json.load(f)
    hooks = data.get("hooks", {})
    hook_count = len(hooks)
    return True, f"valid JSON, {hook_count} hook types"


def check_session_start_hook():
    """SessionStart hook 存在且指向 startup_hook.py"""
    with open(SETTINGS_LOCAL) as f:
        data = json.load(f)
    ss = data.get("hooks", {}).get("SessionStart", [])
    if not ss:
        return False, "SessionStart hook MISSING"
    cmd = str(ss)
    has_startup = "startup_hook.py" in cmd
    return has_startup, "startup_hook.py configured" if has_startup else "MISSING startup_hook.py reference"


def check_stop_hook():
    """Stop hook 存在且指向 heartbeat_hook.py"""
    with open(SETTINGS_LOCAL) as f:
        data = json.load(f)
    stop = data.get("hooks", {}).get("Stop", [])
    if not stop:
        return False, "Stop hook MISSING"
    cmd = str(stop)
    has_hb = "heartbeat_hook" in cmd
    return has_hb, "heartbeat_hook.py configured" if has_hb else "MISSING heartbeat_hook reference"


def check_pretooluse_count():
    """PreToolUse 内层 hooks 总数 ≥ EXPECTED_PRETOOLUSE_COUNT"""
    with open(SETTINGS_LOCAL) as f:
        data = json.load(f)
    ptu = data.get("hooks", {}).get("PreToolUse", [])
    total_hooks = sum(len(e.get("hooks", [])) for e in ptu if isinstance(e, dict))
    entry_count = len(ptu)
    ok = total_hooks >= EXPECTED_PRETOOLUSE_COUNT
    return ok, f"{entry_count} entries, {total_hooks} inner hooks (expected ≥{EXPECTED_PRETOOLUSE_COUNT} inner hooks)"


def check_hook_scripts_exist():
    """所有必需 hook 脚本文件存在"""
    missing = []
    for script in REQUIRED_HOOK_SCRIPTS:
        path = os.path.join(SCRIPTS_DIR, script)
        if not os.path.exists(path):
            missing.append(script)
    return len(missing) == 0, f"all {len(REQUIRED_HOOK_SCRIPTS)} scripts present" if not missing else f"MISSING: {missing}"


def check_pretooluse_has_system_drive():
    """PreToolUse 中包含 system_drive.py (共振引擎)"""
    with open(SETTINGS_LOCAL) as f:
        data = json.load(f)
    ptu = data.get("hooks", {}).get("PreToolUse", [])
    has_sd = any("system_drive.py" in str(entry) for entry in ptu)
    return has_sd, "system_drive.py in PreToolUse" if has_sd else "system_drive.py NOT in PreToolUse — resonance disabled"


def check_hook_timeouts():
    """Hook 超时值不过短 (≥3s)"""
    with open(SETTINGS_LOCAL) as f:
        data = json.load(f)
    issues = []
    for hook_type, entries in data.get("hooks", {}).items():
        for entry in entries:
            if isinstance(entry, dict):
                for h in entry.get("hooks", []):
                    timeout = h.get("timeout", 0)
                    if 0 < timeout < 3:
                        issues.append(f"{hook_type}:{h.get('command','')[:30]} timeout={timeout}s")
    return len(issues) == 0, f"all timeouts ≥3s" if not issues else f"SHORT TIMEOUTS: {issues}"


def check_protected_modules_defined():
    """settings.json 中的 WebSearch/WebFetch block hook 有效"""
    with open(SETTINGS) as f:
        data = json.load(f)
    ptu = data.get("hooks", {}).get("PreToolUse", [])
    has_block = any("websearch-block-hook" in str(e).lower() for e in ptu)
    return has_block, "WebSearch/WebFetch block configured" if has_block else "WARNING: WebSearch block not configured"


def main():
    parser = argparse.ArgumentParser(description="Hooks 配置完整性验收")
    parser.add_argument("--quick", action="store_true", help="仅 JSON 有效性 + 结构")
    args = parser.parse_args()

    print("=" * 62)
    print("  Hooks 配置完整性验收")
    print("=" * 62)

    print("\n── Phase 1: JSON 有效性 ──")
    check("settings.json valid",       check_settings_json)
    check("settings.local.json valid", check_settings_local_json)

    print("\n── Phase 2: Hook 结构 ──")
    check("SessionStart configured",   check_session_start_hook)
    check("Stop configured",           check_stop_hook)
    check("PreToolUse count",          check_pretooluse_count)
    check("PreToolUse has system_drive", check_pretooluse_has_system_drive)
    check("WebSearch block configured", check_protected_modules_defined)

    if not args.quick:
        print("\n── Phase 3: 脚本完整性 ──")
        check("Hook scripts present",  check_hook_scripts_exist)
        check("Hook timeouts ≥3s",      check_hook_timeouts)

    print(f"\n{'='*62}")
    total = PASS + FAIL + WARN
    print(f"  {total} checks: {PASS} pass, {WARN} warn, {FAIL} fail")
    if FAIL > 0:
        print("  退化标志: JSON broken, hooks missing, scripts deleted, resonance disconnected")
    else:
        print("  Hooks configuration OK")
    print(f"{'='*62}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
