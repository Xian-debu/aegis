#!/usr/bin/env python3
"""
一键全系统验收 — 运行所有 validate_*.py 并汇总

设计原则:
  - 每个子模块的输出自带基线解释 (validate_npu.py 模式)
  - 汇总层只做"全部通过?"判断，不重复解释
  - 区分 FAIL (故障) 和 WARN (已知限制/正常边界)
  - --quick 模式跳过语义质量检查，只做结构+服务健康

用法:
  python3 validate_all.py              # 完整验收
  python3 validate_all.py --quick       # 快速验收 (结构+服务)
  python3 validate_all.py --json        # JSON 输出 (供程序化消费)
"""
import subprocess, sys, os, json, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPTS_DIR = "/root/.claude/scripts"

# ═══════════════════════════════════════════════════════
# 模块定义 — 每个模块有独立的 validate 脚本
# ═══════════════════════════════════════════════════════
MODULES = {
    "npu": {
        "script": "npu/validate_npu.py",
        "description": "NPU bge-m3 embedding quality + baselines",
        "always_run": True,
    },
    "mf": {
        "script": "validate_mf.py",
        "description": "Memory Forest integrity + heartbeat freshness",
        "always_run": True,
    },
    "resonance": {
        "script": "validate_resonance.py",
        "description": "Signal resonance rules + engine health",
        "always_run": True,
    },
    "hooks": {
        "script": "validate_hooks.py",
        "description": "Claude Code hooks configuration integrity",
        "always_run": True,
    },
    "services": {
        "script": "validate_services.py",
        "description": "Backend services (Ollama, Docker, NPU, Guardian)",
        "always_run": True,
    },
}


def run_module(name, info, quick=False):
    """运行单个模块的 validate 脚本，返回 (name, success, output)"""
    script_path = os.path.join(SCRIPTS_DIR, info["script"])
    if not os.path.exists(script_path):
        return name, False, f"SCRIPT MISSING: {script_path}", []

    cmd = ["python3", script_path]
    if quick:
        cmd.append("--quick")

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        output = r.stdout
        if r.stderr:
            output += "\n[stderr]\n" + r.stderr
        # Count pass/fail/warn from output
        passes = output.count("\033[32m✓\033[0m") + output.count("[32m✓[0m") + output.count("✓")
        fails = output.count("\033[31m✗\033[0m") + output.count("[31m✗[0m") + output.count("✗")
        warns = output.count("\033[33m⚠\033[0m") + output.count("[33m⚠[0m") + output.count("⚠")
        success = r.returncode == 0
        return name, success, output, [passes, fails, warns]
    except subprocess.TimeoutExpired:
        return name, False, "TIMEOUT (>60s)", [0, 1, 0]
    except Exception as e:
        return name, False, f"ERROR: {e}", [0, 1, 0]


def main():
    parser = argparse.ArgumentParser(description="一键全系统验收")
    parser.add_argument("--quick", action="store_true", help="快速模式 (仅结构+服务健康)")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--module", "-m", action="append", help="仅运行指定模块 (可重复)")
    args = parser.parse_args()

    # Filter modules
    if args.module:
        to_run = {k: v for k, v in MODULES.items() if k in args.module}
    else:
        to_run = MODULES

    if not args.json:
        print("=" * 70)
        print("  全系统验收 — validate_all.py")
        print(f"  模块: {len(to_run)} | 模式: {'quick' if args.quick else 'full'}")
        print("=" * 70)

    # Parallel execution
    results = {}
    with ThreadPoolExecutor(max_workers=min(len(to_run), 5)) as ex:
        futures = {ex.submit(run_module, name, info, args.quick): name for name, info in to_run.items()}
        for future in as_completed(futures):
            name, success, output, counts = future.result()
            results[name] = (success, output, counts)

    # Report
    if args.json:
        report = {}
        for name, (success, output, counts) in sorted(results.items()):
            report[name] = {
                "success": success,
                "pass": counts[0],
                "fail": counts[1],
                "warn": counts[2],
            }
        print(json.dumps(report, indent=2))
        return 0 if all(v[0] for v in results.values()) else 1

    # Text report
    total_pass, total_fail, total_warn = 0, 0, 0
    all_ok = True

    for name in sorted(to_run.keys()):
        if name not in results:
            continue
        success, output, counts = results[name]
        p, f, w = counts[0], counts[1], counts[2]
        total_pass += p
        total_fail += f
        total_warn += w

        info = to_run[name]
        icon = "\033[32m✓\033[0m" if success else "\033[31m✗\033[0m"
        print(f"\n{'─'*70}")
        print(f"  {icon} {name}: {info['description']}")
        print(f"     {p} pass, {f} fail, {w} warn")
        if not success:
            all_ok = False
            # Show last few lines of output for failed modules
            lines = output.strip().split("\n")
            for line in lines[-5:]:
                if "✗" in line or "FAIL" in line or "ERROR" in line or "MISSING" in line:
                    print(f"     {line.strip()[:100]}")

    # Summary
    print(f"\n{'='*70}")
    total = total_pass + total_fail + total_warn
    print(f"  TOTAL: {total} checks across {len(to_run)} modules")
    print(f"  Pass: {total_pass}, Fail: {total_fail}, Warn: {total_warn}")

    if total_fail == 0:
        print("  \033[32mALL MODULES PASS\033[0m — 系统正常")
    else:
        print(f"  \033[31m{total_fail} FAILURES\033[0m — 需要关注")
        print()
        print("  下一步:")
        print("    1. 单独运行失败的 validate 脚本查看详情")
        print("    2. 检查记忆中的已知限制是否解释了这些失败")
        print("    3. 如果所有已有测试通过但你看数字'感觉不对' → 先查基线")
        print("    4. 如果确认是真回归 → 修复 + 更新 validate 脚本的基线")

    print(f"{'='*70}")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
