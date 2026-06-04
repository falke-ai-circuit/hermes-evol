---
name: evol-reflect
description: Phase 2 of evol-cycle. Build in-memory pattern graph from absorb state. Identify adjustment points (where agent is stuck). 0-1 LLM calls. Returns patterns + adjustment_points + anomalies + gaps.
last_used: 2026-06-04
---

# REFLECT — Pattern Synthesis

> Build a graph from absorb state. Cluster patterns. Identify where the agent's circuit conflicts with its actual state. Output drives ADAPT.

## When to load

Load when starting phase 2 of `evol-cycle`. Input is absorb output.

## Input

- Absorb state dict (from `phases/absorb/scripts/collect_state.py`)

## Output contract

```python
{
  "patterns": [
    {"name": str, "weight": float, "sources": [str, ...], "evidence": [str, ...], "first_seen": ts, "last_seen": ts}
  ],
  "clusters": [
    {"name": str, "members": [pattern_name, ...], "weight": float, "hypothesis": str}
  ],
  "adjustment_points": [
    {"kind": "stale_doctrine" | "recurring_orphan" | "missing_capability" | "pending_question_unanswered",
     "where": str, "evidence": str, "weight": float}
  ],
  "anomalies": [str],
  "gaps": [str]  # questions only EXPLORE can answer
}
```

## Algorithm (no LLM needed for the first pass)

1. **Patterns**: extract from `evol_entries[*].reflect.patterns[]`. Weight = max weight seen across occurrences (from `items[].raw_weight` if present, else 0.5). Sources = which evol_entries cite this pattern. Cluster by name.
2. **Doctrine claims**: from absorb's `doctrine_claims[]`. For each, search memory graph (graphiti) for grant/fact that contradicts or supersedes. If grant is newer than doctrine → adjustment_point `stale_doctrine`.
3. **Recurring orphans**: pattern with weight ≥ 0.85 AND zero MEMORY.md entries about resolution → adjustment_point `recurring_orphan`.
4. **Missing capabilities**: doctrine_claim says "X cannot do Y" but pending_questions.md has "can you do Y?" → adjustment_point `missing_capability`.
5. **Pending questions**: any line in `pending_questions` → adjustment_point `pending_question_unanswered`.
6. **Anomalies**: from `evol_entries[*].reflect.anomalies[]` (last 5 entries), unique.
7. **Gaps**: questions like "what does Goran want analyst to do?" → flag for EXPLORE.

## LLM use

If patterns > 20 OR clusters > 5, call LLM (provider from config) to name clusters. Otherwise the deterministic clustering is enough. **No LLM call by default.**

## Anti-Patterns

- ⛔ Hallucinating patterns not in absorb state — every pattern must trace to a circuit file, evol entry, or session.
- ⛔ Skipping stale-doctrine check — that's the most valuable signal in dormant profiles.
- ⛔ Outputting patterns with no sources — violates 3-source rule.

## Gotchas

| Problem | Root cause | Fix |
|---------|-----------|-----|
| Pattern appears 13x but no resolution | detection-without-healing, recurring orphan | flag as adjustment_point |
| Doctrine says "no write authority" but Goran granted it | stale doctrine | cite the grant; propose to update doctrine |
| Pattern is in MEMORY.md 6x already | demote to context, don't re-append | output `demoted: true` |

## Run

```bash
python ~/.hermes/profiles/evol/skills/evol-cycle/phases/reflect/scripts/pattern_graph.py \
  /tmp/evol_absorb_<target>.json > /tmp/evol_reflect_<target>.json
```

## Evolution Log

| Date | Promotion | Source |
|------|-----------|--------|
| 2026-06-04 | Initial | spec at `references/six-phase-skill-layout.md` |
<!-- last_used: 2026-06-04 -->
