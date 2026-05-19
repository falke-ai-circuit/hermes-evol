#!/usr/bin/env python3
"""
AKIS G7 Knowledge Update Script for hermes-evol.
Scans evol.jsonl, extracts gotchas, updates project_knowledge.json.
Usage: python .github/scripts/knowledge.py --update
"""
import json, sys, os
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
KNOWLEDGE_PATH = REPO_ROOT / "project_knowledge.json"
EVOL_LOG = REPO_ROOT.parent / "evol.jsonl"  # In conductor profile dir
CLAUDE_PATH = REPO_ROOT / "CLAUDE.md"

def load_knowledge():
    if KNOWLEDGE_PATH.exists():
        return json.loads(KNOWLEDGE_PATH.read_text())
    return {
        "project": "hermes-evol",
        "last_updated": None,
        "hot_cache": [],
        "gotchas": [],
        "recent_changes": [],
        "architecture": {
            "files": {},
            "phases": ["ABSORB", "REFLECT", "EXPLORE", "EXPRESS", "MEMORIZE"],
            "providers": {}
        }
    }

def extract_gotchas_from_claude():
    """Parse CLAUDE.md gotcha section for structured gotchas."""
    gotchas = []
    if not CLAUDE_PATH.exists():
        return gotchas
    
    content = CLAUDE_PATH.read_text()
    in_gotcha = False
    for line in content.splitlines():
        if line.strip().startswith("### Gotchas"):
            in_gotcha = True
            continue
        if in_gotcha and line.strip().startswith("##"):
            break
        if in_gotcha and line.strip().startswith("- "):
            parts = line.strip()[2:].split(" — ")
            if len(parts) >= 3:
                gotchas.append({
                    "id": parts[0].lower().replace(" ", "-").replace("`", "").replace("__", "-"),
                    "problem": parts[0].strip(),
                    "root_cause": parts[1].strip() if len(parts) > 1 else "",
                    "fix": parts[2].strip() if len(parts) > 2 else "",
                    "severity": "HIGH",
                    "last_hit": None,
                    "hits": 0
                })
    return gotchas

def scan_evol_log():
    """Scan evol.jsonl for recent patterns and cycle data."""
    patterns = []
    if not EVOL_LOG.exists():
        return patterns
    
    try:
        entries = [json.loads(l) for l in EVOL_LOG.read_text().strip().splitlines() if l.strip()]
        # Get last 5 cycles
        for e in entries[-5:]:
            reflect = e.get("reflect", {})
            for p in reflect.get("patterns", []):
                if isinstance(p, str):
                    patterns.append(p)
    except (json.JSONDecodeError, OSError):
        pass
    
    return patterns

def update_knowledge():
    kb = load_knowledge()
    now = datetime.now(timezone.utc).isoformat()
    
    # Update gotchas from CLAUDE.md
    gotchas = extract_gotchas_from_claude()
    existing_ids = {g.get("id") for g in kb.get("gotchas", [])}
    for g in gotchas:
        if g["id"] not in existing_ids:
            kb.setdefault("gotchas", []).append(g)
    
    # Update hot cache from evol.jsonl patterns
    patterns = scan_evol_log()
    if patterns:
        kb["hot_cache"] = kb.get("hot_cache", [])
        # Remove old cache entries
        kb["hot_cache"] = [h for h in kb["hot_cache"] if h.get("weight", 0) > 0.3]
        # Add current patterns
        seen_topics = {h.get("topic") for h in kb["hot_cache"]}
        for p in patterns[:5]:
            if p not in seen_topics:
                kb["hot_cache"].append({
                    "topic": p,
                    "weight": 0.85,
                    "last_hit": now,
                    "files": ["hermes_evol/registry.py"],
                    "note": "From recent EVOL cycle"
                })
    
    kb["last_updated"] = now
    KNOWLEDGE_PATH.write_text(json.dumps(kb, indent=2, ensure_ascii=False) + "\n")
    print(f"Knowledge updated: {KNOWLEDGE_PATH} ({len(kb.get('gotchas', []))} gotchas, {len(kb.get('hot_cache', []))} hot cache)")
    return 0

if __name__ == "__main__":
    if "--update" in sys.argv:
        sys.exit(update_knowledge())
    else:
        print("Usage: python .github/scripts/knowledge.py --update")
        sys.exit(0)
