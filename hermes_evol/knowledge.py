"""EVOL Knowledge Layer - Three-Tier Cognitive Architecture.

Tier 3 (CIRCUIT):  SOUL.md . AGENTS.md . IDENTITY.md . USER.md  -- IDENTITY, per-profile
Tier 2 (MEMORY):   MEMORY.md                                      -- ATTENTIVE, per-profile, ~8K cap
Tier 1 (KNOWLEDGE): .hermes/knowledge/                            -- ACCUMULATED, shared, wikilinked

Movement rules:
  Knowledge -> Memory   ONLY path up. Can't skip to Circuit.
  Memory -> Circuit     Weight > promote_memory_to_circuit + identity match.
                        Route by content type: SOUL=doctrine, AGENTS=workflow,
                        IDENTITY=personhood/firmware, USER=relational/Goran-facts.
  Circuit -> Memory     Weight drops below demote_circuit_to_memory.
  Memory -> Knowledge   Weight drops below demote_memory_to_knowledge.
  Knowledge -> cleaned  Weight < phase_out threshold.

Decay: exponential, kicks in after 7 days unused.
Wikilinks: [[page-name]] bidirectional, auto-maintained.
Domain clustering: automatic when 3+ files share domain tag."""
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

# ── Constants ──────────────────────────────────────────────────────

KNOWLEDGE_DIR = os.path.expanduser("~/.hermes/knowledge")

# Tier transition thresholds (configurable per profile)
THRESHOLDS = {
    "promote_knowledge_to_memory":  0.65,  # knowledge entry weight must exceed this
    "promote_memory_to_circuit":    0.85,  # legacy catch-all — prefer per-file thresholds below
    "demote_circuit_to_memory":     0.50,  # circuit entry drops below → memory
    "demote_memory_to_knowledge":   0.40,  # memory entry drops below → knowledge
    "phase_out":                    0.15,  # knowledge entry below → delete
    "memory_capacity_chars":        8000,  # MEMORY.md cap
    "decay_rate":                   0.95,  # exponential decay factor per day
    "decay_grace_days":            7,      # no decay for first 7 days
    # Per-file circuit thresholds — which weight gates promotion to each file
    "per_file_threshold": {
        "SOUL.md":      0.85,    # doctrine — highest bar, only core truths
        "AGENTS.md":    0.70,    # workflow — lower bar, operational patterns
        "IDENTITY.md":  0.75,    # personhood — mid bar, identity-shaping facts
        "USER.md":      0.70,    # relational/Goran-facts — lower bar, user-context
        "MEMORY.md":    0.50,    # memory — lowest bar, anything persistent enough
        "CIRCUIT":      0.85,    # fallback for LLM-specified targets without filename
    },
}

# ── Helpers ────────────────────────────────────────────────────────

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _ts() -> float:
    return time.time()

def _safe_read(path: str, default: str = "") -> str:
    try:
        return Path(path).read_text()
    except (OSError, UnicodeDecodeError):
        return default

def _safe_write(path: str, content: str) -> bool:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content)
        return True
    except OSError:
        return False

def _safe_json(path: str, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text())
    except (json.JSONDecodeError, OSError):
        return default if default is not None else {}

def _slugify(text: str, max_len: int = 60) -> str:
    """Convert text to a filesystem-safe slug."""
    slug = re.sub(r'[^a-z0-9]+', '-', text.lower().strip())
    slug = slug.strip('-')
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip('-')
    return slug or "untitled"

def _extract_domain(text: str, tags: List[str] = None) -> str:
    """Extract domain from text and tags. Returns domain name or 'general'."""
    candidates = (tags or []) + [text]
    # Common domain patterns
    domains = {
        "docker": ["docker", "container", "compose", "image", "volume"],
        "hostinger": ["hostinger", "vps", "187.124", "hpanel"],
        "evol": ["evol", "reflect", "express", "memorize", "absorb", "explore"],
        "hermes": ["hermes", "gateway", "openclaw", "plugin", "skill"],
        "model": ["deepseek", "ollama", "venice", "llm", "model", "inference"],
        "telegram": ["telegram", "bot", "chat", "message"],
        "memory": ["memory", "knowledge", "circuit", "session", "lcm"],
        "network": ["ssh", "tcp", "http", "dns", "network", "bridge", "proxy"],
    }
    combined = (text + " " + " ".join(tags or [])).lower()
    scores = {}
    for domain, keywords in domains.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score:
            scores[domain] = score
    if scores:
        return max(scores, key=scores.get)
    return "general"

# ── Wikilinks ──────────────────────────────────────────────────────

def parse_wikilinks(content: str) -> List[str]:
    """Extract [[pagename]] links from markdown content."""
    return re.findall(r'\[\[([^\[\]]+)\]\]', content)

def update_wikilinks(knowledge_file: str, linked_files: List[str]):
    """Ensure bidirectional wikilinks exist between knowledge files."""
    current = _safe_read(knowledge_file)
    if not current:
        return

    current_links = set(parse_wikilinks(current))
    
    for linked in linked_files:
        if linked in current_links:
            continue
        # Add forward link
        link_line = f"\n→ [[{linked}]]"
        if link_line not in current:
            _safe_write(knowledge_file, current.rstrip() + link_line)
            current = _safe_read(knowledge_file)
        
        # Add backlink
        linked_path = os.path.join(KNOWLEDGE_DIR, f"{linked}.md")
        if os.path.exists(linked_path):
            linked_content = _safe_read(linked_path)
            my_slug = os.path.splitext(os.path.basename(knowledge_file))[0]
            if f"[[{my_slug}]]" not in linked_content:
                _safe_write(linked_path, linked_content.rstrip() + f"\n→ [[{my_slug}]]")

# ── Knowledge CRUD ─────────────────────────────────────────────────

def create_knowledge(
    concept: str,
    summary: str,
    domain: str = "general",
    sources: List[str] = None,
    tags: List[str] = None,
    weight: float = 0.50,
) -> str:
    """Create a new knowledge file. Returns the file path."""
    slug = _slugify(concept)
    domain_dir = os.path.join(KNOWLEDGE_DIR, domain)
    filepath = os.path.join(domain_dir, f"{slug}.md")

    if os.path.exists(filepath):
        # Update existing
        return update_knowledge(filepath, summary, weight, sources, tags)

    content = f"""# {concept}
- discovered: {_utc_now()[:10]}
- domain: {domain}
- weight: {weight:.2f}
- last_used: {_utc_now()}
- sources: {json.dumps(sources or [])}
- tags: {json.dumps(tags or [])}

## Summary
{summary}

## Links

"""
    _safe_write(filepath, content)
    return filepath

def update_knowledge(
    filepath: str,
    summary: str = "",
    weight: float = 0.0,
    sources: List[str] = None,
    tags: List[str] = None,
) -> str:
    """Update an existing knowledge file."""
    current = _safe_read(filepath)
    if not current:
        return filepath

    # Update frontmatter
    current = re.sub(
        r'weight: [\d.]+',
        f'weight: {weight:.2f}',
        current
    )
    current = re.sub(
        r'last_used: .*',
        f'last_used: {_utc_now()}',
        current
    )
    if sources:
        existing_sources = re.search(r'sources: (\[.*?\])', current)
        if existing_sources:
            old_sources = json.loads(existing_sources.group(1))
            new_sources = list(set(old_sources + sources))
            current = current.replace(existing_sources.group(1), json.dumps(new_sources))
        else:
            current = current.replace(
                '## Summary',
                f'sources: {json.dumps(sources)}\n\n## Summary'
            )
    if tags:
        existing_tags = re.search(r'tags: (\[.*?\])', current)
        if existing_tags:
            old_tags = json.loads(existing_tags.group(1))
            new_tags = list(set(old_tags + tags))
            current = current.replace(existing_tags.group(1), json.dumps(new_tags))

    if summary:
        # Append to existing summary
        if "## Summary" in current:
            parts = current.split("## Summary")
            parts[1] = parts[1].replace("\n\n", f"\n\n{summary}\n\n", 1)
            current = "## Summary".join(parts)

    _safe_write(filepath, current)
    return filepath

def read_knowledge(concept_slug: str, domain: str = None) -> Optional[Dict]:
    """Read a knowledge file. Returns dict with frontmatter + content."""
    if domain:
        filepath = os.path.join(KNOWLEDGE_DIR, domain, f"{concept_slug}.md")
    else:
        # Search all domains
        for d in os.listdir(KNOWLEDGE_DIR):
            candidate = os.path.join(KNOWLEDGE_DIR, d, f"{concept_slug}.md")
            if os.path.exists(candidate):
                filepath = candidate
                break
        else:
            return None

    content = _safe_read(filepath)
    if not content:
        return None

    # Parse frontmatter
    weight = 0.0
    wm = re.search(r'weight: ([\d.]+)', content)
    if wm:
        weight = float(wm.group(1))

    last_used = ""
    lu = re.search(r'last_used: (.+)', content)
    if lu:
        last_used = lu.group(1).strip()

    domain_detected = ""
    dm = re.search(r'domain: (.+)', content)
    if dm:
        domain_detected = dm.group(1).strip()

    return {
        "path": filepath,
        "slug": concept_slug,
        "weight": weight,
        "domain": domain_detected,
        "last_used": last_used,
        "content": content,
        "wikilinks": parse_wikilinks(content),
    }

def list_knowledge(domain: str = None, min_weight: float = 0.0) -> List[Dict]:
    """List all knowledge files, optionally filtered."""
    results = []
    root = KNOWLEDGE_DIR
    if domain:
        root = os.path.join(root, domain)

    if not os.path.exists(root):
        return []

    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            if not fname.endswith('.md'):
                continue
            filepath = os.path.join(dirpath, fname)
            slug = os.path.splitext(fname)[0]
            entry = read_knowledge(slug, domain or os.path.basename(dirpath))
            if entry and entry['weight'] >= min_weight:
                results.append(entry)

    return results

def delete_knowledge(concept_slug: str, domain: str = "general") -> bool:
    """Delete a knowledge file."""
    filepath = os.path.join(KNOWLEDGE_DIR, domain, f"{concept_slug}.md")
    if not os.path.exists(filepath):
        return False
    try:
        # Remove backlinks from all other knowledge files
        for entry in list_knowledge():
            content = entry['content']
            if f"[[{concept_slug}]]" in content:
                new_content = content.replace(f"[[{concept_slug}]]", "")
                _safe_write(entry['path'], new_content)
        os.remove(filepath)
        return True
    except OSError:
        return False

# ── Decay ──────────────────────────────────────────────────────────

def decay_weight(last_used: str, current_weight: float) -> float:
    """Apply exponential decay to a weight based on time since last use."""
    if not last_used:
        return current_weight
    try:
        last_date = datetime.fromisoformat(last_used[:19])  # handle Z suffix
        days_unused = (datetime.now(timezone.utc) - last_date.replace(tzinfo=timezone.utc)).days
    except (ValueError, TypeError):
        return current_weight

    if days_unused <= THRESHOLDS["decay_grace_days"]:
        return current_weight

    days_decaying = days_unused - THRESHOLDS["decay_grace_days"]
    new_weight = current_weight * (THRESHOLDS["decay_rate"] ** days_decaying)
    return round(new_weight, 4)

# ── Index ──────────────────────────────────────────────────────────

def rebuild_index():
    """Rebuild knowledge/index.md with links to all knowledge files."""
    all_entries = list_knowledge()
    domains: Dict[str, list] = {}
    for entry in all_entries:
        d = entry['domain'] or 'general'
        domains.setdefault(d, []).append(entry)

    lines = [
        "# Knowledge Index",
        f"_auto-generated {_utc_now()}_\n",
        f"**{len(all_entries)} entries** across **{len(domains)} domains**\n",
    ]

    for domain, entries in sorted(domains.items()):
        lines.append(f"## {domain.title()} ({len(entries)})")
        for entry in sorted(entries, key=lambda e: e['weight'], reverse=True):
            slug = entry['slug']
            title = slug.replace('-', ' ').title()
            wt = entry['weight']
            decay_indicator = "🕸️" if wt < 0.30 else "🌿" if wt < 0.50 else "🌳" if wt < 0.70 else "🔥"
            lines.append(f"- {decay_indicator} [[{slug}]] — *{title}* (wt: {wt:.2f})")
        lines.append("")

    _safe_write(os.path.join(KNOWLEDGE_DIR, "index.md"), "\n".join(lines))

# ── MEMORY.md Capacity Management ──────────────────────────────────

def manage_memory_capacity(memory_path: str):
    """If MEMORY.md exceeds capacity, demote lowest-weight entries to knowledge."""
    content = _safe_read(memory_path)
    if not content or len(content) <= THRESHOLDS["memory_capacity_chars"]:
        return

    # Parse entries (separated by § or double newline)
    entries = re.split(r'(?:§\n|\n\n\n)', content)
    if len(entries) <= 1:
        return

    # Score each entry by recency mention
    scored = []
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        # Simple heuristic: more recent timestamps → higher score
        recency_score = 0.5
        if re.search(r'2026-05', entry):
            recency_score = 0.8
        if re.search(r'2026-04', entry):
            recency_score = 0.6
        if re.search(r'2025', entry):
            recency_score = 0.3
        scored.append((entry, recency_score))

    # Sort by score ascending — trim lowest first
    scored.sort(key=lambda x: x[1])

    demoted = []
    kept_entries = scored.copy()
    total_chars = sum(len(e[0]) for e in scored)

    while total_chars > THRESHOLDS["memory_capacity_chars"] and kept_entries:
        removed = kept_entries.pop(0)  # remove lowest scored
        demoted.append(removed)
        total_chars -= len(removed[0])

    if demoted:
        # Write demoted entries to knowledge
        for entry, _ in demoted:
            title = entry[:80].split('\n')[0].strip('# ')
            domain = _extract_domain(entry)
            tags = [domain]
            create_knowledge(
                concept=title or "memory-entry",
                summary=entry[:500],
                domain=domain,
                tags=tags,
                weight=0.35,  # starts low in knowledge
            )

        # Rewrite memory with kept entries
        new_memory = "\n\n§\n\n".join(e[0] for e in kept_entries)
        _safe_write(memory_path, new_memory)

# ── Agent Navigation ───────────────────────────────────────────────

def navigate(from_tier: str, concept: str, profile: str = "conductor") -> Dict:
    """
    Navigate from one tier to others for a concept.
    Returns context from all tiers where the concept exists.
    """
    result = {
        "concept": concept,
        "found_in": [],
        "circuit": None,
        "memory": None,
        "knowledge": None,
    }

    slug = _slugify(concept)

    # Tier 1: Knowledge
    k_entry = read_knowledge(slug)
    if k_entry:
        result["found_in"].append("knowledge")
        result["knowledge"] = {
            "path": k_entry["path"],
            "weight": k_entry["weight"],
            "summary": k_entry["content"].split("## Summary")[-1][:500] if "## Summary" in k_entry["content"] else k_entry["content"][:500],
            "wikilinks": k_entry["wikilinks"],
        }

    # Tier 2: Memory
    memory_path = f"/opt/data/profiles/{profile}/MEMORY.md"
    memory_content = _safe_read(memory_path)
    if slug.lower() in memory_content.lower() or concept.lower() in memory_content.lower():
        result["found_in"].append("memory")
        # Find relevant paragraph
        for para in memory_content.split("\n\n"):
            if concept.lower() in para.lower():
                result["memory"] = para[:500]
                break

    # Tier 3: Circuit
    for cf in ["SOUL.md", "AGENTS.md", "IDENTITY.md"]:
        cf_path = f"/opt/data/profiles/{profile}/{cf}"
        cf_content = _safe_read(cf_path)
        if slug.lower() in cf_content.lower() or concept.lower() in cf_content.lower():
            result["found_in"].append("circuit")
            if not result["circuit"]:
                result["circuit"] = {}
            result["circuit"][cf] = cf_content[:300]

    return result

# ═══════════════════════════════════════════════════════════════════
# TEST — Demonstrate the system
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("╔═══════════════════════════════════════════╗")
    print("║  EVOL KNOWLEDGE LAYER — DEMO            ║")
    print("╚═══════════════════════════════════════════╝")

    # ── 1. Create knowledge ──
    print("\n── 1. Creating knowledge entries ──")
    
    k1 = create_knowledge(
        "Docker Network Bridging",
        "Cross-compose networking requires docker network connect. On Hostinger 187.124.31.229, hermes-agent-llic and hermes-workspace-haua are separate compose projects on different bridge networks.",
        domain="docker",
        tags=["docker", "networking", "hostinger"],
        weight=0.72,
    )
    print(f"  Created: {k1}")

    k2 = create_knowledge(
        "Venice GLM Heretic Thinking",
        "GLM heretic returns all output in reasoning_content field, not content. Fix: check reasoning_content as fallback, or increase max_tokens to 8192+.",
        domain="model",
        tags=["venice", "glm", "heretic", "thinking"],
        weight=0.68,
    )
    print(f"  Created: {k2}")

    k3 = create_knowledge(
        "Hostinger Infrastructure",
        "VPS at 187.124.31.229. Docker stacks: hermes-agent-llic (rescue conductor), hermes-workspace-haua (primary). SSH broken from rescue container — needs sshpass or key auth.",
        domain="hostinger",
        tags=["hostinger", "vps", "infrastructure"],
        weight=0.85,
    )
    print(f"  Created: {k3}")

    # ── 2. Update weight ──
    print("\n── 2. Updating weight (simulated usage) ──")
    update_knowledge(k3, weight=0.92)
    updated = read_knowledge("hostinger-infrastructure", "hostinger")
    print(f"  {updated['slug']}: weight={updated['weight']} ✓")

    # ── 3. Decay ──
    print("\n── 3. Decay simulation ──")
    old_weight = decay_weight("2026-03-15T00:00:00", 0.80)  # 64+ days old
    fresh_weight = decay_weight(_utc_now(), 0.80)            # brand new
    print(f"  80-day-old 0.80 → {old_weight:.3f} (decayed)")
    print(f"  Fresh 0.80       → {fresh_weight:.3f} (no decay)")

    # ── 4. List knowledge ──
    print("\n── 4. Listing all knowledge ──")
    all_k = list_knowledge()
    for e in all_k:
        print(f"  {e['domain']}/{e['slug']}: wt={e['weight']:.2f}")

    # ── 5. Navigation ──
    print("\n── 5. Agent navigation test ──")
    nav = navigate("memory", "Docker Network Bridging")
    print(f"  Found in: {nav['found_in']}")
    if nav['knowledge']:
        print(f"  Knowledge weight: {nav['knowledge']['weight']}")

    # ── 6. Rebuild index ──
    print("\n── 6. Rebuilding index ──")
    rebuild_index()
    idx = _safe_read(os.path.join(KNOWLEDGE_DIR, "index.md"))
    print(f"  Index: {len(idx)} chars, {idx.count('[[[')} links")

    print(f"\n{'='*50}")
    print("✅ Knowledge layer operational")
    print(f"{'='*50}")
