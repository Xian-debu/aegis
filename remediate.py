"""AEGIS Auto-Remediation — detect known issues and auto-fix.

Risk levels:
  SAFE: Can auto-fix without confirmation (e.g., clean __pycache__)
  CAUTION: Auto-fix with notification (e.g., restart ollama)
  DANGER: Never auto-fix, only suggest (e.g., docker rm)
"""
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from aegis.config import GUARDIAN_DB, DISK_WARN_PCT, SWAP_WARN_PCT


class RiskLevel(Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DANGER = "danger"


@dataclass
class FixAction:
    issue: str
    description: str
    risk: RiskLevel
    command: str
    verify_command: str = ""


# ── Known issue → fix mapping ─────────────────────────

KNOWN_FIXES = [
    FixAction(
        issue="ollama:0",
        description="Ollama has 0 models or is unreachable",
        risk=RiskLevel.CAUTION,
        command="systemctl restart ollama && sleep 3 && ollama list",
        verify_command="ollama list | tail -n +2 | wc -l",
    ),
    FixAction(
        issue="disk:",
        description="Disk usage high — clean pip cache and apt cache",
        risk=RiskLevel.SAFE,
        command="rm -rf ~/.cache/pip && apt-get clean 2>/dev/null; echo 'cleaned'",
        verify_command="df -h / | awk 'NR==2{print $5}'",
    ),
    FixAction(
        issue="swap",
        description="Swap usage high — drop caches",
        risk=RiskLevel.CAUTION,
        command="sync && echo 3 > /proc/sys/vm/drop_caches 2>/dev/null; echo 'done'",
        verify_command="free -h | awk 'NR==3{print $3}'",
    ),
    FixAction(
        issue="zombie",
        description="Zombie sessions detected — mark as CLOSED",
        risk=RiskLevel.SAFE,
        command=f"python3 -c \"import sqlite3; c=sqlite3.connect('{GUARDIAN_DB}'); c.execute(\\\"UPDATE sessions SET status='CLOSED' WHERE status='ZOMBIE'\\\"); c.commit(); print('cleaned')\"",
    ),
    FixAction(
        issue="docker:",
        description="Docker exited containers — prune",
        risk=RiskLevel.SAFE,
        command="docker container prune -f 2>/dev/null; echo 'pruned'",
        verify_command="docker ps -a --format '{{.Names}}:{{.Status}}' | grep -c Exited",
    ),
]


def diagnose() -> list[dict]:
    """Run diagnosis and return matched known issues with fix suggestions."""
    findings = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for fix in KNOWN_FIXES:
        # Check if the issue pattern matches current state
        if _check_issue(fix.issue):
            findings.append({
                "issue": fix.issue,
                "description": fix.description,
                "risk": fix.risk.value,
                "command": fix.command,
                "auto_applicable": fix.risk == RiskLevel.SAFE,
                "timestamp": now,
            })

    return findings


def apply_fix(fix_desc: str, dry_run: bool = True) -> dict:
    """Apply a known fix. Only SAFE-level fixes can auto-apply."""
    for fix in KNOWN_FIXES:
        if fix.issue in fix_desc or fix_desc in fix.description:
            if fix.risk == RiskLevel.DANGER:
                return {"applied": False, "error": "DANGER-level fix requires manual confirmation"}
            if dry_run:
                return {"applied": False, "dry_run": True, "would_run": fix.command}

            try:
                r = subprocess.run(fix.command, shell=True, capture_output=True, text=True, timeout=30)
                return {
                    "applied": r.returncode == 0,
                    "stdout": r.stdout.strip()[:500],
                    "stderr": r.stderr.strip()[:500],
                    "command": fix.command,
                }
            except Exception as e:
                return {"applied": False, "error": str(e)}

    return {"applied": False, "error": "No matching fix found"}


def _check_issue(pattern: str) -> bool:
    """Check if a known issue pattern matches current system state."""
    if pattern == "ollama:0":
        try:
            r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
            models = len([l for l in r.stdout.splitlines() if l.strip()]) - 1
            return models <= 0
        except Exception:
            return True  # Can't reach ollama → issue exists

    if pattern.startswith("disk:"):
        try:
            r = subprocess.run(["df", "-P", "/"], capture_output=True, text=True, timeout=5)
            pct = int(r.stdout.splitlines()[-1].split()[4].rstrip("%"))
            # DISK_WARN_PCT imported at module level
            return pct > DISK_WARN_PCT
        except Exception:
            return False

    if pattern == "swap":
        try:
            r = subprocess.run(["free", "-b"], capture_output=True, text=True, timeout=5)
            swap_line = r.stdout.splitlines()[2].split()
            swap_used = int(swap_line[2])
            swap_total = int(swap_line[1])
            # SWAP_WARN_PCT imported at module level
            return (swap_used / swap_total * 100) > SWAP_WARN_PCT if swap_total > 0 else False
        except Exception:
            return False

    if pattern == "zombie":
        try:
            import sqlite3
            conn = sqlite3.connect(f"file:{GUARDIAN_DB}?mode=ro", uri=True)
            count = conn.execute("SELECT COUNT(*) FROM sessions WHERE status='ZOMBIE'").fetchone()[0]
            conn.close()
            return count > 0
        except Exception:
            return False

    if pattern.startswith("docker:"):
        try:
            r = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.Status}}"],
                capture_output=True, text=True, timeout=5,
            )
            return "Exited" in r.stdout
        except Exception:
            return False

    return False
