# AEGIS — Autonomous Environment Guardian & Integration System

A lightweight, zero-dependency integration framework that unifies Claude Code subsystems into a coherent autonomous operating substrate with mechanical guardrails against LLM hallucination and diagnostic errors.

**v2.0.0 — Fool-Proof Guardrail System (Evolution 3)**

## Three layers, one system

```
L1: Claude Guardian (systemd daemon)  →  KNOWS WHEN
    Session lifecycle, health monitoring, crash detection

L2: Memory Forest (structured memory) →  KNOWS WHAT
    Task tracking, heartbeat, GC, decision history

L3: RAG Knowledge Base (vector search) →  KNOWS HOW
    Semantic search, RAG generation, web expansion

L4: System Drive Engine (NEW v2.0)   →  PREVENTS MISTAKES
    Signal resonance, mechanical PREFLIGHT, validate matrix, guardrail hooks
```

## Quick Start

```bash
git clone https://github.com/Xian-debu/aegis.git
cd aegis && bash install.sh
aegis status
aegis health
```

## Commands

| Command | Description |
|---------|-------------|
| `aegis status` | Three-layer dashboard (Guardian + Forest + KB) |
| `aegis health` | Health check with issues and warnings |
| `aegis sync` | Full bridge sync across all layers |
| `aegis search <query>` | Cross-layer search (KB + memory forest) |
| `aegis diagnose` | Detect known issues + suggest fixes |
| `aegis fix <issue>` | Apply a known fix (`--dry-run` to preview) |

## Guardrail System (v2.0.0)

### Validate Matrix
One command to verify the entire system:

```bash
python3 scripts/validate_all.py --quick    # All 5 modules, 70+ checks
python3 scripts/validate_all.py             # Full semantic validation
python3 scripts/validate_all.py --json      # Machine-readable output
```

| Module | Checks | Coverage |
|--------|--------|----------|
| `validate_mf.py` | 20 | Memory Forest integrity + heartbeat freshness |
| `validate_resonance.py` | 14 | Signal resonance rules + engine health |
| `validate_hooks.py` | 14 | Claude Code hooks configuration integrity |
| `validate_services.py` | 14 | Ollama + Docker + NPU + Guardian + n8n |
| `validate_npu.py` | 8 | NPU bge-m3 embedding quality + baselines |

### System Drive Engine (`scripts/system_drive.py`)

Autonomous context-aware signal resonance:
- **SessionStart**: Injects health + validation + PREFLIGHT + anti-pattern warnings into Claude's context
- **PreToolUse**: Matches tool calls to relevant memories; guards Edit/Write on protected modules
- **Signal Resonance**: 32 error→memory + 27 tool→memory + 11 context signals + 10 anti-pattern rules (`scripts/signals.json`)

### Guardrail Architecture

```
SessionStart Hook
  └→ system_drive.py cmd_session_start()
       ├→ Health snapshot (6 metrics)
       ├→ Task continuity scan
       ├→ Context signal matching (11 scenarios)
       ├→ validate_all.py --quick (auto-run, results injected)
       ├→ PREFLIGHT checklist (mechanical steps)
       ├→ STOP signals (5 anti-patterns)
       ├→ Known failure patterns (from feedback history)
       └→ Previous session guardrail violations

PreToolUse Hook
  └→ system_drive.py cmd_pre_tool()
       ├→ Tool→memory resonance (27 rules)
       ├→ Error→memory matching (32 rules)
       └→ Guardrail check (Edit/Write on validated module → warn + log)
```

## Architecture

```
┌──────────────────────────────────────────────────┐
│                   aegis CLI                        │
│         status | health | sync | diagnose          │
├────────────────────┬─────────────────────────────┤
│     bridges/       │      core/                   │
│  guardian_forest   │  ┌──────────────────────┐   │
│  forest_kb         │  │ monitor.py           │   │
│  guardian_kb       │  │  Unified dashboard   │   │
│                    │  ├──────────────────────┤   │
│                    │  │ remediate.py         │   │
│                    │  │  Auto-fix engine     │   │
│                    │  └──────────────────────┘   │
├────────────────────┴─────────────────────────────┤
│     scripts/  (NEW v2.0.0)                        │
│  system_drive.py    validate_all.py               │
│  signals.json       validate_mf.py                │
│  startup_hook.py    validate_resonance.py         │
│  heartbeat_hook.py  validate_hooks.py             │
│  guardian_client.py validate_services.py          │
│  mf.py              validate_npu.py               │
└──────────────────────────────────────────────────┘
```

## Configuration

All paths are derived from environment variables. Nothing is hardcoded.

| Variable | Default | Description |
|----------|---------|-------------|
| `AEGIS_HOME` | `~/.claude` | Base directory for all AEGIS data |
| `GUARDIAN_DIR` | `$AEGIS_HOME/guardian` | Guardian daemon state |
| `MEMORY_ROOT` | `$AEGIS_HOME/projects/-root/memory` | Memory Forest root |
| `KB_ROOT` | `~/rag-kb` | RAG Knowledge Base root |
| `AEGIS_DISK_WARN` | `80` | Disk usage warning threshold (%) |
| `AEGIS_MEM_WARN` | `90` | Memory usage warning threshold (%) |

See `config.py` for all options.

## Requirements

- Python 3.10+
- Zero external dependencies (stdlib only)
- Optional: Claude Guardian daemon (systemd), RAG-KB, Memory Forest

## Risk Handling

AEGIS classifies auto-fixes by risk level:

| Level | Example | Behavior |
|-------|---------|----------|
| SAFE | Clean pip cache, prune docker | Auto-apply with `aegis fix` |
| CAUTION | Restart ollama, drop caches | Apply with notification |
| DANGER | Delete data, system config | Never auto-apply, suggest only |

## Testing

```bash
cd aegis
python3 tests/test_bridge_gf.py      # Guardian↔Forest bridge
python3 tests/test_bridge_fk.py      # Forest↔KB bridge
python3 tests/test_bridge_gk.py      # Guardian↔KB bridge
python3 tests/test_integration.py    # Full integration
python3 scripts/validate_all.py      # Guardrail validation matrix
```

## Evolution History

| Version | Date | Theme |
|---------|------|-------|
| v1.0.0 | 2026-05-13 | Three-layer bridge: Guardian + Forest + KB |
| v2.0.0 | 2026-05-14 | Fool-proof guardrails: validate matrix + mechanical PREFLIGHT + PreToolUse gates |

## Companion Projects

| Project | Description |
|---------|-------------|
| [memory-forest](https://github.com/Xian-debu/memory-forest) | Structured memory framework for Claude Code |
| [DoubaoCLI](https://github.com/Xian-debu/DoubaoCLI) | Browser automation framework |
| [aigc-decheck-workflow](https://github.com/Xian-debu/aigc-decheck-workflow) | AI-generated text detection workflow |

## License

MIT
