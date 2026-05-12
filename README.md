# AEGIS — Autonomous Environment Guardian & Integration System

A lightweight, zero-dependency integration framework that unifies three Claude Code subsystems into a coherent autonomous operating substrate.

**Three layers, one system:**

```
L1: Claude Guardian (systemd daemon)  →  KNOWS WHEN
    Session lifecycle, health monitoring, crash detection

L2: Memory Forest (structured memory) →  KNOWS WHAT
    Task tracking, heartbeat, GC, decision history

L3: RAG Knowledge Base (vector search) →  KNOWS HOW
    Semantic search, RAG generation, web expansion

AEGIS BRIDGES make them work as one:
    Guardian→Forest: session heartbeat sync, crash→DORMANT
    Forest→KB:      node indexing, gap→task creation
    Guardian→KB:    health snapshots, session summaries
```

## Quick Start

```bash
# Install
git clone https://github.com/Xian-debu/aegis.git
cd aegis && bash install.sh

# Verify
aegis status
aegis health
aegis sync       # Full bridge synchronization
aegis diagnose   # Detect known issues
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

## Architecture

```
┌──────────────────────────────────────────────────┐
│                   aegis CLI                       │
│         status | health | sync | diagnose         │
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
│                  config.py                        │
│    All paths from env vars, zero hardcoding       │
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
| `AEGIS_PROJECT_MAP` | `""` | cwd→project mapping: `/path=name;/p2=n2` |

See `config.py` for all options.

## Requirements

- Python 3.10+
- Zero external dependencies (stdlib only)
- Optional: Claude Guardian daemon (systemd), RAG-KB, Memory Forest

## Companion Projects

AEGIS bridges three subsystems. Each can be used independently:

| Project | Description |
|---------|-------------|
| [memory-forest](https://github.com/Xian-debu/memory-forest) | Structured memory framework for Claude Code |
| [DoubaoCLI](https://github.com/Xian-debu/DoubaoCLI) | Browser automation framework |
| [aigc-decheck-workflow](https://github.com/Xian-debu/aigc-decheck-workflow) | AI-generated text detection workflow |

## Testing

```bash
cd aegis
python3 tests/test_bridge_gf.py      # Guardian↔Forest bridge
python3 tests/test_bridge_fk.py      # Forest↔KB bridge
python3 tests/test_bridge_gk.py      # Guardian↔KB bridge
python3 tests/test_integration.py    # Full integration
```

## Risk Handling

AEGIS classifies auto-fixes by risk level:

| Level | Example | Behavior |
|-------|---------|----------|
| SAFE | Clean pip cache, prune docker | Auto-apply with `aegis fix` |
| CAUTION | Restart ollama, drop caches | Apply with notification |
| DANGER | Delete data, system config | Never auto-apply, suggest only |

## License

MIT
