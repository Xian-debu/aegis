"""Bridge L2: Memory Forest ↔ RAG Knowledge Base.

Bidirectional sync:
  Forest→KB: Index forest nodes as KB documents (with memory_refs backlinks)
  KB→Forest: KB search results can reference forest nodes, KB gaps can create tasks
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/root/rag-kb")
sys.path.insert(0, "/root/.claude/scripts")

from aegis.config import MEMORY_ROOT, KB_ROOT, AUTO_INDEX_MEMORY_ON_START


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ── Forest → KB: Index memory nodes ───────────────────

def index_forest_to_kb(tree_filter: str = None) -> dict:
    """Index memory forest nodes into the knowledge base.

    Uses kb index-memory under the hood.
    Returns {nodes_scanned, nodes_indexed, chunks_created, errors}
    """
    result = {"nodes_scanned": 0, "nodes_indexed": 0, "chunks_created": 0, "errors": []}

    try:
        args = [sys.executable or "python3", str(KB_ROOT / "scripts" / "kb_cli.py"), "index-memory"]
        if tree_filter:
            args.extend(["--tree", tree_filter])

        r = subprocess.run(args, capture_output=True, text=True, timeout=120)

        # Parse output
        for line in r.stdout.split("\n"):
            if "Scanned:" in line:
                result["nodes_scanned"] = int(re.search(r"(\d+)", line).group(1))
            elif "Indexed:" in line:
                result["nodes_indexed"] = int(re.search(r"(\d+)", line).group(1))
            elif "Chunks:" in line:
                result["chunks_created"] = int(re.search(r"(\d+)", line).group(1))

        if r.returncode != 0:
            result["errors"].append(r.stderr.strip()[:500])
    except Exception as e:
        result["errors"].append(str(e))

    return result


# ── KB → Forest: Search memory in KB ──────────────────

def search_kb_for_memory(query: str, top_k: int = 5) -> list[dict]:
    """Search KB for memory-forest-indexed documents.

    Returns list of {chunk_id, document_id, content, score, memory_refs, ...}
    """
    try:
        r = subprocess.run(
            [sys.executable or "python3", str(KB_ROOT / "scripts" / "kb_cli.py"),
             "search", query, "--source", "memory", "--top-k", str(top_k)],
            capture_output=True, text=True, timeout=30,
        )
        # Parse kb search output (text format)
        results = []
        lines = r.stdout.split("\n")
        current = None
        for line in lines:
            score_match = re.match(r"\s*\[([0-9.]+)\]\s+(.+?)\s+\((.+?)\)", line)
            if score_match:
                if current:
                    results.append(current)
                current = {
                    "score": float(score_match.group(1)),
                    "title": score_match.group(2).strip(),
                    "format": score_match.group(3).strip(),
                }
            elif current and line.strip().startswith("mem-"):
                current["memory_id"] = line.strip().split()[0].replace("mem-", "")
        if current:
            results.append(current)
        return results
    except Exception:
        return []


# ── Forest health from KB perspective ─────────────────

def get_kb_forest_health() -> dict:
    """Check KB health regarding memory forest coverage."""
    try:
        r = subprocess.run(
            [sys.executable or "python3", str(KB_ROOT / "scripts" / "kb_cli.py"), "status"],
            capture_output=True, text=True, timeout=10,
        )
        output = r.stdout

        docs_match = re.search(r"Documents:\s+(\d+)", output)
        chunks_match = re.search(r"Chunks:\s+(\d+)", output)
        vectors_match = re.search(r"Vectors:\s+(\d+)", output)

        # Count memory-sourced documents
        r2 = subprocess.run(
            [sys.executable or "python3", str(KB_ROOT / "scripts" / "kb_cli.py"),
             "list", "--source", "memory"],
            capture_output=True, text=True, timeout=10,
        )
        mem_count = len(re.findall(r"\[memory\]", r2.stdout))

        return {
            "total_docs": int(docs_match.group(1)) if docs_match else 0,
            "total_chunks": int(chunks_match.group(1)) if chunks_match else 0,
            "total_vectors": int(vectors_match.group(1)) if vectors_match else 0,
            "memory_docs": mem_count,
            "coverage_pct": round(mem_count / max(1, int(docs_match.group(1) or 1)) * 100, 1),
            "timestamp": _now(),
        }
    except Exception as e:
        return {"error": str(e), "timestamp": _now()}


# ── Gap detection → Forest task creation ──────────────

def create_task_from_kb_gap(query: str, top_score: float, result_count: int) -> bool:
    """If KB shows a knowledge gap, create a task node in the forest.

    Returns True if a task was created.
    """
    if top_score > 0.4 and result_count >= 3:
        return False  # No gap

    task_slug = re.sub(r"[^a-z0-9]+", "-", query.lower())[:50]
    task_dir = MEMORY_ROOT / "projects-tree" / "knowledge-gaps"
    task_dir.mkdir(parents=True, exist_ok=True)
    task_file = task_dir / f"gap-{task_slug}.md"

    if task_file.exists():
        return False

    severity = "HIGH" if top_score < 0.2 else "MEDIUM"
    content = f"""---
id: GAP-{task_slug[:20]}
type: LEAF
tree: projects
layer: L1
status: ACTIVE
created: {_today()}
heartbeat: '{_today()}'
priority: {severity}
tags:
- knowledge-gap
- auto-generated
---

# Knowledge Gap: {query[:80]}

**Detected**: {_today()}
**Severity**: {severity} (top_score={top_score:.3f}, results={result_count})

The knowledge base has insufficient coverage for this query. Consider:
1. Running `kb expand "{query[:60]}"` to web-search and ingest
2. Manually adding relevant documents
3. Marking this gap as resolved if the information exists outside KB

Auto-generated by AEGIS Forest↔KB bridge.
"""
    try:
        task_file.write_text(content, encoding="utf-8")
        return True
    except Exception:
        return False
