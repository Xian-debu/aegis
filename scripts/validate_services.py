#!/usr/bin/env python3
"""
服务健康验收脚本
一键检查所有后端服务: Ollama, Docker, NPU, Guardian, n8n

设计原则: 每个服务有明确的状态定义 ("正常" vs "需关注" vs "故障")。
已知正常情况:
  - latex-dev 和 dev 容器可能 Exited (按需启动，不使用时自动退出)
  - NPU 服务在 Windows 宿主侧, 通过 localhost:8898 桥接
  - Guardian 通过 systemd 管理，systemctl status 判断

用法:
  python3 validate_services.py              # 完整验收
  python3 validate_services.py --quick       # 仅核心服务 (Ollama + Docker + NPU)
"""
import subprocess, json, sys, os, argparse, requests

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


def run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT", -1
    except Exception as e:
        return "", str(e), -1


# ═══════════════════════════════════════════════════════
# Ollama
# ═══════════════════════════════════════════════════════
EXPECTED_OLLAMA_MODELS_MIN = 2  # 最少模型数


def check_ollama_running():
    """Ollama 守护进程运行中"""
    out, err, rc = run("ollama list 2>/dev/null", timeout=10)
    ok = rc == 0 and "NAME" in out
    return ok, f"ollama list OK" if ok else f"ollama not responding (rc={rc})"


def check_ollama_models():
    """至少有 EXPECTED_OLLAMA_MODELS_MIN 个模型可用"""
    out, err, rc = run("ollama list 2>/dev/null | tail -n +2 | wc -l", timeout=10)
    count = int(out.strip()) if out.strip().isdigit() else 0
    ok = count >= EXPECTED_OLLAMA_MODELS_MIN
    return ok, f"{count} models (min={EXPECTED_OLLAMA_MODELS_MIN})"


# ═══════════════════════════════════════════════════════
# Docker
# ═══════════════════════════════════════════════════════
ALWAYS_RUNNING_CONTAINERS = ["n8n"]        # 应始终运行的容器
ON_DEMAND_CONTAINERS = ["dev", "latex-dev"]  # 按需运行，Exited 正常


def check_docker_running():
    """Docker daemon 运行中"""
    out, err, rc = run("docker ps 2>&1", timeout=10)
    ok = rc == 0 and "CONTAINER" in out
    return ok, "docker responsive" if ok else f"docker not responsive: {err[:80]}"


def check_critical_containers():
    """关键容器运行中"""
    for container in ALWAYS_RUNNING_CONTAINERS:
        out, err, rc = run(f"docker ps --filter name={container} --format '{{{{.Status}}}}'", timeout=10)
        if not out.strip():
            return False, f"'{container}' NOT RUNNING"
    return True, f"critical containers OK: {', '.join(ALWAYS_RUNNING_CONTAINERS)}"


def check_on_demand_containers():
    """按需容器状态 (Exited=正常)"""
    statuses = []
    for container in ON_DEMAND_CONTAINERS:
        out, err, rc = run(f"docker ps -a --filter name={container} --format '{{{{.Status}}}}'", timeout=10)
        status = out.strip()[:30] if out.strip() else "NOT FOUND"
        statuses.append(f"{container}:{status}")
    return None, f"on-demand: {', '.join(statuses)} (Exited=OK)"


# ═══════════════════════════════════════════════════════
# NPU (Windows 宿主桥接)
# ═══════════════════════════════════════════════════════
def check_npu_health():
    """NPU 推理服务可达 (Windows 宿主 localhost 桥接)"""
    try:
        r = requests.get("http://localhost:8898/health", timeout=5)
        d = r.json()
        ok = d.get("status") == "ok"
        return ok, f"status={d.get('status')}, device={d.get('device','?')}, model={d.get('model','?')}"
    except requests.exceptions.Timeout:
        return False, "TIMEOUT — NPU service not reachable (Windows host may be off)"
    except requests.exceptions.ConnectionError:
        return False, "CONNECTION REFUSED — NPU service not running on Windows host"
    except Exception as e:
        return False, f"ERROR: {e}"


# ═══════════════════════════════════════════════════════
# Guardian
# ═══════════════════════════════════════════════════════
def check_guardian_running():
    """Claude Guardian daemon 运行中"""
    out, err, rc = run("systemctl is-active claude-guardian 2>&1", timeout=5)
    ok = out.strip() == "active"
    return ok, f"systemd: {out.strip()}" if ok else f"systemd: {out.strip()}"


# ═══════════════════════════════════════════════════════
# Disk & Memory (from signals.json health_checks)
# ═══════════════════════════════════════════════════════
DISK_WARN_PCT = 80
MEM_WARN_PCT = 90


def check_disk_usage():
    """磁盘使用率 < DISK_WARN_PCT%"""
    out, err, rc = run("df -h / | awk 'NR==2{print $5}'", timeout=5)
    pct_str = out.strip().replace("%", "")
    try:
        pct = int(pct_str)
    except ValueError:
        return None, f"could not parse: '{out.strip()}'"
    ok = pct < DISK_WARN_PCT
    return ok, f"{pct}% (warn={DISK_WARN_PCT}%)"


def check_memory_usage():
    """内存使用率 < MEM_WARN_PCT%"""
    out, err, rc = run("free | awk 'NR==2{printf \"%.0f\", $3/$2*100}'", timeout=5)
    try:
        pct = int(out.strip())
    except ValueError:
        return None, f"could not parse: '{out.strip()}'"
    ok = pct < MEM_WARN_PCT
    return ok, f"{pct}% (warn={MEM_WARN_PCT}%)"


# ═══════════════════════════════════════════════════════
# n8n
# ═══════════════════════════════════════════════════════
def check_n8n_health():
    """n8n webhook 端点可达"""
    try:
        r = requests.get("http://localhost:8900/workflow/health", timeout=5)
        if r.status_code == 404:
            return None, "health endpoint returns 404 (n8n webhook server may not have this route)"
        ok = r.status_code == 200
        return ok, f"HTTP {r.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "CONNECTION REFUSED — n8n webhook server not running"
    except Exception as e:
        return False, f"ERROR: {e}"


def main():
    parser = argparse.ArgumentParser(description="Service Health 验收")
    parser.add_argument("--quick", action="store_true", help="仅核心服务 (Ollama + Docker + NPU + Disk)")
    args = parser.parse_args()

    print("=" * 62)
    print("  Service Health 验收")
    print("=" * 62)

    print("\n── Core Services ──")
    check("Ollama daemon",      check_ollama_running)
    check("Ollama models",      check_ollama_models)
    check("Docker daemon",      check_docker_running)
    check("Critical containers", check_critical_containers)
    check("NPU inference",      check_npu_health)
    check("Disk usage",         check_disk_usage)
    check("Memory usage",       check_memory_usage)

    if not args.quick:
        print("\n── Extended Services ──")
        check("On-demand containers",   check_on_demand_containers)
        check("Claude Guardian",        check_guardian_running)
        check("n8n webhook server",     check_n8n_health)

    print(f"\n{'='*62}")
    total = PASS + FAIL + WARN
    print(f"  {total} checks: {PASS} pass, {WARN} warn, {FAIL} fail")
    if FAIL > 0:
        print("  故障: 核心服务不可达，功能受限")
    else:
        print("  All core services OK")
    print(f"{'='*62}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
