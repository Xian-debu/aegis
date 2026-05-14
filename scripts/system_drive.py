#!/usr/bin/env python3
"""System Drive Engine — autonomous context-aware signal resonance.

Layers:
  L0: Signal bus — system_state.json read/write
  L1: Session guardian — health check + task scan + context injection
  L2: Intent resonance — signal matching against current context
  L3: Auto-maintenance — periodic health snapshots + GC

Called by:
  - SessionStart hook: generate context injection for new sessions
  - PreToolUse hook: match tool patterns to memories
  - Cron: periodic health snapshots
  - CLI: 'mf drive-status' for manual inspection
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# ── Paths ──────────────────────────────────────────────
SIGNALS_PATH = Path("/root/.claude/signals.json")
STATE_PATH = Path("/root/.claude/system_state.json")
MEMORY_ROOT = Path("/root/.claude/projects/-root/memory")
SCRIPTS_DIR = Path("/root/.claude/scripts")
PROJECTS_DIR = MEMORY_ROOT / "projects-tree"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ═══════════════════════════════════════════════════════════
# L0: SIGNAL BUS
# ═══════════════════════════════════════════════════════════

def load_signals() -> dict:
    """Load signal definitions."""
    if SIGNALS_PATH.exists():
        return json.loads(SIGNALS_PATH.read_text())
    return {}


def load_state() -> dict:
    """Load current system state snapshot."""
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            pass
    return {"sessions": [], "health_snapshots": [], "active_contexts": []}


def save_state(state: dict) -> None:
    """Persist system state snapshot."""
    state["_updated"] = _now()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def record_session_start(session_id: str = "") -> dict:
    """Record a new session in the state bus."""
    state = load_state()
    session = {
        "id": session_id or os.environ.get("CLAUDE_SESSION_ID", "unknown"),
        "started": _now(),
        "cwd": os.getcwd(),
    }
    # Keep last 20 sessions
    state.setdefault("sessions", []).append(session)
    if len(state["sessions"]) > 20:
        state["sessions"] = state["sessions"][-20:]
    save_state(state)
    return session


# ═══════════════════════════════════════════════════════════
# L1: SESSION GUARDIAN — HEALTH + TASK SCAN
# ═══════════════════════════════════════════════════════════

def health_snapshot() -> dict:
    """Run all health checks defined in signals.json."""
    signals = load_signals()
    checks = signals.get("health_checks", {})
    results = {}

    for name, cfg in checks.items():
        cmd = cfg.get("command", "")
        warn = cfg.get("warn_threshold", "")
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            output = r.stdout.strip()
            results[name] = {"ok": True, "output": output}

            if warn and warn.rstrip("%") in output:
                pct = int(output.split("%")[0]) if "%" in output else 0
                threshold = int(warn.rstrip("%"))
                if pct >= threshold:
                    results[name]["ok"] = False
                    results[name]["warning"] = f"{output} >= {warn}"
        except Exception as e:
            results[name] = {"ok": False, "error": str(e)}

    return results


def scan_dormant_tasks() -> list[dict]:
    """Scan memory forest for DORMANT/ACTIVE/RUNNING tasks, ordered by priority."""
    PRIORITY_ORDER = {"ABSOLUTE": 0, "CRITICAL": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 4, "BACKGROUND": 5}

    tasks = []
    if not PROJECTS_DIR.exists():
        return tasks

    for md_file in PROJECTS_DIR.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        # Quick parse: extract frontmatter status and priority
        lines = content.split("\n")
        status = priority = heartbeat = node_id = ""
        in_fm = False
        for line in lines[:50]:
            if line.strip() == "---":
                if not in_fm:
                    in_fm = True
                    continue
                else:
                    break
            if in_fm:
                if line.startswith("status:"):
                    status = line.split(":", 1)[1].strip().strip("'\"")
                elif line.startswith("priority:"):
                    priority = line.split(":", 1)[1].strip().strip("'\"")
                elif line.startswith("heartbeat:"):
                    heartbeat = line.split(":", 1)[1].strip().strip("'\"")
                elif line.startswith("id:"):
                    node_id = line.split(":", 1)[1].strip().strip("'\"")

        if status in ("DORMANT", "ACTIVE", "RUNNING"):
            # Extract title from first heading
            title = ""
            for line in lines[50:]:
                if line.startswith("# "):
                    title = line[2:].strip()
                    break

            tasks.append({
                "id": node_id,
                "file": str(md_file.relative_to(MEMORY_ROOT)),
                "status": status,
                "priority": priority,
                "heartbeat": heartbeat,
                "title": title,
                "priority_score": PRIORITY_ORDER.get(priority, 99),
            })

    tasks.sort(key=lambda t: (t["priority_score"], t["heartbeat"] or ""))
    return tasks


def match_context(cwd: str = "", keywords: list[str] = None) -> list[dict]:
    """Match current context against signal definitions. Returns triggered signals."""
    signals = load_signals()
    context_signals = signals.get("context_signals", {})
    triggered = []

    if keywords is None:
        keywords = []

    for name, sig in context_signals.items():
        match = sig.get("match", {})
        score = 0
        reasons = []

        # CWD match
        cwd_patterns = match.get("cwd_contains", [])
        if cwd_patterns and cwd:
            for p in cwd_patterns:
                if p in cwd:
                    score += 2
                    reasons.append(f"cwd:{p}")
                    break

        # Keyword match
        kw_patterns = match.get("keywords", [])
        if kw_patterns and keywords:
            matched_kw = [kw for kw in keywords if any(p in kw.lower() for p in kw_patterns)]
            if matched_kw:
                score += len(matched_kw)
                reasons.append(f"kw:{','.join(matched_kw[:3])}")

        # File match (from tool calls)
        file_patterns = match.get("files_touched", [])
        if file_patterns and keywords:
            for p in file_patterns:
                if any(p.replace("*", "") in kw for kw in keywords):
                    score += 1
                    reasons.append(f"file:{p}")
                    break

        if score >= 2:  # Threshold for triggering
            triggered.append({
                "signal": name,
                "score": score,
                "reasons": reasons,
                "action": sig.get("action", {}),
            })

    triggered.sort(key=lambda t: t["score"], reverse=True)
    return triggered


# ═══════════════════════════════════════════════════════════
# L2: INTENT RESONANCE — TOOL PATTERN MATCHING
# ═══════════════════════════════════════════════════════════

def resonance_for_tool(tool_name: str, tool_input: dict = None) -> dict:
    """Match a tool call against resonance rules. Returns preload suggestions.

    For tool_pattern_to_memory, builds a composite search string from
    tool_name + command/args/content so regex patterns can match concretely.
    """
    signals = load_signals()
    rules = signals.get("resonance_rules", {})

    result = {
        "memories": [],
        "error_patterns": [],
    }

    # Build composite search string from tool input
    search_text = tool_name
    if tool_input:
        # Extract the most searchable fields from the input
        for field in ("command", "file_path", "path", "query", "prompt", "text"):
            val = tool_input.get(field, "")
            if val:
                search_text += " " + str(val)
                break
        # Fallback: concatenate all values
        if search_text == tool_name:
            search_text += " " + " ".join(str(v) for v in tool_input.values() if isinstance(v, str))

    # Check tool pattern matches against the composite search string
    tool_patterns = rules.get("tool_pattern_to_memory", {})
    for pattern, memory_ids in tool_patterns.items():
        if _pattern_match(search_text, pattern):
            result["memories"].extend(memory_ids)

    # Check error patterns in tool input
    error_patterns = rules.get("error_pattern_to_memory", {})
    if tool_input:
        input_str = json.dumps(tool_input) if isinstance(tool_input, dict) else str(tool_input)
        for pattern, memory_ids in error_patterns.items():
            if _pattern_match(input_str, pattern):
                result["error_patterns"].append({
                    "pattern": pattern,
                    "memories": memory_ids,
                })

    # Deduplicate
    result["memories"] = list(dict.fromkeys(result["memories"]))
    return result


def _pattern_match(text: str, pattern: str) -> bool:
    """Regex pattern match (case-insensitive). Falls back to substring."""
    import re
    try:
        return bool(re.search(pattern, text, re.IGNORECASE))
    except re.error:
        return pattern.lower() in text.lower()


# ═══════════════════════════════════════════════════════════
# L2.5: GUARDRAIL CHECK (Evolution 3)
# ═══════════════════════════════════════════════════════════

# Module→validate_script mapping
PROTECTED_MODULES = {
    "/root/.claude/scripts/npu/": "npu/validate_npu.py",
    "/root/.claude/scripts/": "validate_all.py",  # generic
    "/root/.claude/projects/-root/memory/": "validate_mf.py",
    "/root/.claude/settings.json": "validate_hooks.py",
    "/root/.claude/settings.local.json": "validate_hooks.py",
    "/root/.claude/signals.json": "validate_resonance.py",
    "/root/rag-kb/": "validate_services.py",  # services covers ollama+rag
}

GUARDRAIL_LOG = "/root/.claude/guardian/guardrail_violations.json"


def _guardrail_check(tool_name: str, tool_input: dict):
    """Check if an Edit/Write operation targets a protected module.
    Log violations to guardrail_violations.json for next SessionStart.
    """
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return

    # Find matching protected module
    matched_validate = None
    matched_module = None
    for module_path, validate_script in PROTECTED_MODULES.items():
        if file_path.startswith(module_path):
            matched_validate = validate_script
            matched_module = module_path
            break

    if not matched_validate:
        return

    validate_full_path = os.path.join("/root/.claude/scripts", matched_validate)
    if not os.path.exists(validate_full_path):
        return

    # Check if validate script passes (quick mode, 10s timeout)
    try:
        r = subprocess.run(
            ["python3", validate_full_path, "--quick"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            # Validate passes — editing a known-good module is risky
            violation = {
                "time": _now(),
                "tool": tool_name,
                "file": file_path,
                "module": matched_module,
                "pattern": "edit_validated_module",
                "detail": f"Editing {file_path} while {matched_validate} passes. This module is known-good. Your modification may be unnecessary.",
                "validate_script": matched_validate,
            }
            _log_guardrail_violation(violation)
            print(f"[guard] WARNING: {matched_validate} PASSES — editing {os.path.basename(file_path)} may be unnecessary. Check memory baselines first.", file=sys.stderr)
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass


def _log_guardrail_violation(violation: dict):
    """Log a guardrail violation to the state file."""
    try:
        os.makedirs(os.path.dirname(GUARDRAIL_LOG), exist_ok=True)
        violations = []
        if os.path.exists(GUARDRAIL_LOG):
            with open(GUARDRAIL_LOG) as f:
                violations = json.load(f)
        violations.append(violation)
        # Keep last 20
        if len(violations) > 20:
            violations = violations[-20:]
        with open(GUARDRAIL_LOG, "w") as f:
            json.dump(violations, f, indent=2)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
# L3: SESSION CONTEXT INJECTION (for SessionStart stdout)
# ═══════════════════════════════════════════════════════════

def generate_context_injection(cwd: str = "") -> str:
    """Generate context block for injection into session system prompt.

    This is the MAIN output of the system drive — it gets injected via
    SessionStart hook stdout into Claude's context at session start.

    Evolution 3: Added validation summary, PREFLIGHT mechanical reminder,
    anti-pattern STOP signals, and guardrail state.
    """
    lines = []
    lines.append("<!-- SYSTEM-DRIVE-CONTEXT -->")
    lines.append("")

    # 1. System health
    health = health_snapshot()
    issues = [k for k, v in health.items() if not v.get("ok")]
    if issues:
        lines.append("## System Health (ISSUES DETECTED)")
        for name in issues:
            h = health[name]
            lines.append(f"- **{name}**: {h.get('warning', h.get('error', 'unknown'))}")
        lines.append("")
    else:
        lines.append("## System Health: OK")
        for key in ("disk", "memory", "gpu"):
            if key in health and health[key].get("ok"):
                lines.append(f"- {key}: {health[key].get('output', '?')}")
        lines.append("")

    # 2. Dormant tasks
    tasks = scan_dormant_tasks()
    if tasks:
        lines.append("## Pending Tasks (auto-detected)")
        for t in tasks[:5]:
            age = ""
            if t.get("heartbeat"):
                try:
                    hb_date = datetime.strptime(str(t["heartbeat"])[:10], "%Y-%m-%d")
                    days = (datetime.now() - hb_date).days
                    if days > 0:
                        age = f" [{days}d ago]"
                except (ValueError, TypeError):
                    pass
            prio_icon = {"ABSOLUTE": "⚡", "CRITICAL": "🔴", "HIGH": "🟡", "MEDIUM": "🟢"}.get(t["priority"], "⚪")
            lines.append(f"- {prio_icon} **{t['title'] or t['id']}** ({t['status']}){age}")
        lines.append("")

    # 3. Context match
    cwd_keywords = _extract_cwd_keywords(cwd)
    triggered = match_context(cwd, cwd_keywords)
    if triggered:
        lines.append("## Auto-Detected Context")
        for t in triggered[:2]:
            action = t["action"]
            lines.append(f"- **{action.get('description', t['signal'])}** (signal: {t['signal']}, score: {t['score']})")
            if action.get("preload_memories"):
                lines.append(f"  - Relevant memories: {', '.join(action['preload_memories'][:5])}")
            if action.get("ensure_services"):
                lines.append(f"  - Ensure services: {', '.join(action['ensure_services'])}")
        lines.append("")

    # 4. Git state for RAG-KB (if in context)
    if "/root/rag-kb" in cwd or any("rag" in kw.lower() for kw in cwd_keywords):
        try:
            r = subprocess.run(
                ["git", "-C", "/root/rag-kb", "log", "--oneline", "-3"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                lines.append("## RAG-KB Git State")
                lines.append("```")
                lines.append(r.stdout.strip())
                lines.append("```")
                lines.append("")
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════
    # EVOLUTION 3: 防呆机械注入
    # ═══════════════════════════════════════════════════════════

    # 5. Validation summary (quick mode, non-blocking, 10s timeout)
    lines.append("## Guardrail: Validation Status")
    validate_script = "/root/.claude/scripts/validate_all.py"
    if os.path.exists(validate_script):
        try:
            r = subprocess.run(
                ["python3", validate_script, "--quick", "--json"],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0:
                mod_results = json.loads(r.stdout)
                failed = {k: v for k, v in mod_results.items() if not v.get("success")}
                if failed:
                    lines.append("VALIDATION FAILURES — run manually before any code changes:")
                    for mod, info in failed.items():
                        lines.append(f"  python3 /root/.claude/scripts/validate_{mod}.py  # fail={info.get('fail',0)}")
                    lines.append("IF ALL VALIDATIONS PASS but you think something is wrong → check memory baselines first.")
                else:
                    lines.append(f"validate_all.py --quick: ALL {len(mod_results)} MODULES PASS")
                    lines.append("If you are about to diagnose or modify any system, your hypothesis is probably wrong unless you have NEW evidence not covered by these validations.")
            else:
                lines.append(f"validate_all.py exited {r.returncode} — run manually to diagnose")
        except subprocess.TimeoutExpired:
            lines.append("validate_all.py timed out (>15s) — run manually if needed")
        except Exception as e:
            lines.append(f"validate_all.py error: {e}")
    lines.append("")

    # 6. PREFLIGHT mechanical checklist (always visible)
    lines.append("## PREFLIGHT: Mandatory Before Any Diagnosis/Modification")
    lines.append("Before you edit code or claim something is broken, mechanically execute:")
    lines.append("1. `grep -i '<topic>' /root/.claude/projects/-root/memory/MEMORY.md` — memory grep")
    lines.append("2. `python3 /root/.claude/scripts/validate_all.py --quick` — run existing tests")
    lines.append("3. If project has CLAUDE.md / ROOT.md / README → read it first")
    lines.append("4. If memory has '已知限制' / '已知基线' / '注意' / '不要' → those are HARD constraints")
    lines.append("")
    lines.append("STOP immediately if you find yourself:")
    lines.append("- Designing your own test to 'verify' a hypothesis (without checking memory first)")
    lines.append("- Judging something as bug because 'this number looks wrong' (without checking baselines)")
    lines.append("- Modifying code >3 lines without understanding WHY")
    lines.append("- Spending >3 turns 'exploring' without checking memory or running ws")
    lines.append("- Using ws with run_in_background")
    lines.append("")

    # 7. Anti-pattern injection — distilled from feedback memories
    lines.append("## Known LLM Failure Patterns (from feedback memories)")
    lines.append("These are patterns I (Claude) have fallen into before. DO NOT REPEAT:")
    lines.append("- **NPU误诊 (2026-05-14)**: Saw cos=0.55 → judged as 'pooling bug' → modified npu_server.py")
    lines.append("  REALITY: 0.55 is bge-m3 baseline. 9/9 tests already passed. validate_npu.py would have caught this.")
    lines.append("- **ws使用不当 (2026-05-14)**: Used run_in_background for ws → results not available when needed")
    lines.append("  REALITY: ws --quick returns in <10s. Never background it.")
    lines.append("- **论文审稿误判**: Reviewed old PDF → hallucinated problems → fabricated references to please reviewer")
    lines.append("  REALITY: Read code first, check dates, never fabricate.")
    lines.append("- **数据驱动画图违反**: Hardcoded fake data in TikZ figures → figure/data/text inconsistency")
    lines.append("  REALITY: All data must come from measurement. Data→pipeline→figure/text unidirectional traceability.")
    lines.append("")

    # 8. Available validate scripts (always visible, so LLM knows they exist)
    lines.append("## Available Validate Scripts (run before modifying any protected module)")
    validate_dir = "/root/.claude/scripts"
    if os.path.isdir(validate_dir):
        vscripts = sorted([
            f for f in os.listdir(validate_dir)
            if f.startswith("validate_") and f.endswith(".py")
        ])
        for vs in vscripts:
            lines.append(f"- `python3 {validate_dir}/{vs}`")
    lines.append("")

    # 9. Guardrail violation state from previous session (if any)
    guardrail_state_file = "/root/.claude/guardian/guardrail_violations.json"
    if os.path.exists(guardrail_state_file):
        try:
            with open(guardrail_state_file) as f:
                violations = json.load(f)
            if violations:
                lines.append("## Previous Session Guardrail Violations")
                for v in violations[-5:]:
                    lines.append(f"- [{v.get('time','?')}] {v.get('pattern','?')}: {v.get('detail','?')}")
                lines.append("")
        except Exception:
            pass

    lines.append("<!-- /SYSTEM-DRIVE-CONTEXT -->")
    return "\n".join(lines)


def _extract_cwd_keywords(cwd: str) -> list[str]:
    """Extract keywords from cwd path for signal matching."""
    keywords = []
    path_map = {
        "/root/rag-kb": ["kb", "rag", "knowledge", "ingest", "search"],
        "/root/project/framework": ["training", "model", "framework", "classifier"],
        "/root/project": ["project", "framework"],
        "/root/tex_project": ["latex", "tex", "thesis", "论文", "compile"],
        "/root/.claude": ["claude", "hook", "config", "skill", "memory"],
        "/root/models": ["model", "ollama", "gguf", "download"],
    }
    for path, kws in path_map.items():
        if path in cwd:
            keywords.extend(kws)
    return keywords


# ═══════════════════════════════════════════════════════════
# CLI / HOOK INTERFACE
# ═══════════════════════════════════════════════════════════

def cmd_status():
    """mf drive-status — show system drive state."""
    print("═══ System Drive Status ═══")
    state = load_state()
    sessions = state.get("sessions", [])
    if sessions:
        last = sessions[-1]
        print(f"Last session: {last.get('started','?')} (id: {last.get('id','?')[:12]}...)")

    health = health_snapshot()
    print("\nHealth:")
    for name, info in health.items():
        icon = "✅" if info.get("ok") else "⚠️"
        output = info.get("output", info.get("error", "?"))
        print(f"  {icon} {name}: {output}")

    tasks = scan_dormant_tasks()
    if tasks:
        print(f"\nPending tasks ({len(tasks)}):")
        for t in tasks[:10]:
            print(f"  [{t['priority']}] {t['title'] or t['id']} ({t['status']} @ {t.get('heartbeat','?')[:10]})")


def cmd_session_start():
    """Called by SessionStart hook. Outputs context injection to stdout."""
    session_id = os.environ.get("CLAUDE_SESSION_ID", "")
    cwd = os.getcwd()

    # Record session
    record_session_start(session_id)

    # Generate and output context injection
    injection = generate_context_injection(cwd)
    print(injection)


def cmd_pre_tool(tool_name: str, tool_input: str = ""):
    """Called by PreToolUse hook. Outputs memory suggestions + guardrail checks."""
    try:
        input_dict = json.loads(tool_input) if tool_input else {}
    except json.JSONDecodeError:
        input_dict = {"input": tool_input}

    # Resonance matching
    result = resonance_for_tool(tool_name, input_dict)
    if result["memories"]:
        print(f"[drive] Relevant memories: {', '.join(result['memories'][:3])}", file=sys.stderr)
    if result["error_patterns"]:
        for ep in result["error_patterns"]:
            print(f"[drive] Error pattern '{ep['pattern']}' matched → {', '.join(ep['memories'][:2])}", file=sys.stderr)

    # Evolution 3: Guardrail check for Edit/Write operations
    if tool_name in ("Edit", "Write") and input_dict:
        _guardrail_check(tool_name, input_dict)


def cmd_health_snapshot():
    """Periodic health snapshot (for cron)."""
    state = load_state()
    health = health_snapshot()
    state.setdefault("health_snapshots", []).append({
        "time": _now(),
        "health": health,
    })
    # Keep last 50
    if len(state["health_snapshots"]) > 50:
        state["health_snapshots"] = state["health_snapshots"][-50:]
    save_state(state)

    issues = [k for k, v in health.items() if not v.get("ok")]
    if issues:
        print(f"[{_today()}] Health issues: {', '.join(issues)}", file=sys.stderr)
    else:
        print(f"[{_today()}] Health OK: disk={health.get('disk',{}).get('output','?')}, mem={health.get('memory',{}).get('output','?')}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: system_drive.py <status|session-start|pre-tool|health-snapshot>", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "status":
        cmd_status()
    elif cmd == "session-start":
        cmd_session_start()
    elif cmd == "pre-tool":
        cmd_pre_tool(sys.argv[2] if len(sys.argv) > 2 else "", sys.argv[3] if len(sys.argv) > 3 else "")
    elif cmd == "health-snapshot":
        cmd_health_snapshot()
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
