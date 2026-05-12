"""AEGIS central configuration.

All paths derive from environment variables with sensible defaults.
No hardcoded user paths — portable across machines.

Environment variables:
  AEGIS_HOME       Base directory (default: ~/.claude)
  GUARDIAN_DIR     Guardian state dir (default: $AEGIS_HOME/guardian)
  MEMORY_ROOT      Memory forest root (default: $AEGIS_HOME/projects/-root/memory)
  KB_ROOT          RAG knowledge base root (default: ~/rag-kb)
"""
import os
from pathlib import Path


def _env_path(name: str, default: str) -> Path:
    val = os.environ.get(name, "")
    return Path(val) if val else Path(default).expanduser().resolve()


AEGIS_HOME = _env_path("AEGIS_HOME", "~/.claude")
GUARDIAN_DIR = _env_path("GUARDIAN_DIR", str(AEGIS_HOME / "guardian"))
GUARDIAN_DB = GUARDIAN_DIR / "state.db"
GUARDIAN_SOCK = GUARDIAN_DIR / "guardian.sock"
GUARDIAN_LOG = GUARDIAN_DIR / "guardian.log"
GUARDIAN_PID = GUARDIAN_DIR / "guardian.pid"

MEMORY_ROOT = _env_path("MEMORY_ROOT", str(AEGIS_HOME / "projects" / "-root" / "memory"))
PROJECTS_DIR = MEMORY_ROOT / "projects-tree"
EXPERIENCES_DIR = MEMORY_ROOT / "experiences-tree"
SYSTEM_DIR = MEMORY_ROOT / "system-tree"

KB_ROOT = _env_path("KB_ROOT", "~/rag-kb")
KB_SCRIPTS = AEGIS_HOME / "scripts"

# ── Health thresholds ─────────────────────────────────
DISK_WARN_PCT = int(os.environ.get("AEGIS_DISK_WARN", "80"))
MEM_WARN_PCT = int(os.environ.get("AEGIS_MEM_WARN", "90"))
GPU_MEM_WARN_PCT = int(os.environ.get("AEGIS_GPU_WARN", "90"))
SWAP_WARN_PCT = int(os.environ.get("AEGIS_SWAP_WARN", "80"))

# ── Session thresholds ─────────────────────────────────
IDLE_TIMEOUT_SEC = int(os.environ.get("AEGIS_IDLE_TIMEOUT", "600"))
ZOMBIE_TIMEOUT_SEC = int(os.environ.get("AEGIS_ZOMBIE_TIMEOUT", "300"))
SESSION_MAX_AGE_DAYS = int(os.environ.get("AEGIS_SESSION_MAX_AGE", "30"))

# ── Bridge behavior ───────────────────────────────────
AUTO_INDEX_MEMORY_ON_START = os.environ.get("AEGIS_AUTO_INDEX", "1") == "1"
AUTO_HEALTH_TO_KB = os.environ.get("AEGIS_AUTO_HEALTH_KB", "1") == "1"
AUTO_CRASH_TO_DORMANT = os.environ.get("AEGIS_AUTO_CRASH_DORMANT", "1") == "1"
AUTO_REMEDIATE = os.environ.get("AEGIS_AUTO_REMEDIATE", "0") == "1"

# ── Project path → forest project mapping ─────────────
# Users should customize this for their own projects.
# Format: {"/path/to/project": "forest-project-name"}
PROJECT_PATH_MAP = {}
_map_env = os.environ.get("AEGIS_PROJECT_MAP", "")
if _map_env:
    for pair in _map_env.split(";"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            PROJECT_PATH_MAP[k.strip()] = v.strip()
else:
    # Defaults — users should override via AEGIS_PROJECT_MAP env var
    PROJECT_PATH_MAP = {}
