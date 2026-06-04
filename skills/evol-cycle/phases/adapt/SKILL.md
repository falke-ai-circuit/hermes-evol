---
name: evol-adapt
description: Phase 3 of evol-cycle. Compare reflect adjustment_points to current circuit state. Produce a justified adjustment_plan with evidence for each proposed edit. Empty plan is valid.
last_used: 2026-06-04
---

# ADAPT — Propose Circuit Adjustments

> Diff between reflect findings and current circuit state. Justify every proposed change with evidence. Empty plan is valid.

## When to load

Load when starting phase 3 of `evol-cycle`. Inputs: reflect output + absorb state.

## Input

- Reflect state dict
- Absorb state dict (for circuit file contents)

## Output contract

```python
{
  "adjustment_plan": [
    {
      "file": "MEMORY.md",  # relative to profile dir
      "current_excerpt": "§ identity-staleness-analyst...",  # exact text to find
      "proposed_text": "## 2026-MM-DD update: ...",
      "evidence": "reflect.adjustment_points[0] + graphiti grant dated 2026-MM-DD",
      "weight": 0.92,
      "action": "append" | "replace" | "none"
    }
  ],
  "summary": "Proposed N changes: 2 appends to MEMORY.md, 1 update to IDENTITY.md reflect_count"
}
```

## Algorithm (no LLM by default)

For each adjustment_point in reflect:
1. If `stale_doctrine` → propose `append` to MEMORY.md with the newer grant
2. If `recurring_orphan` → propose `append` to AGENTS.md gates table, OR demote if already in MEMORY.md 5+ times
3. If `pending_question_unanswered` → no automatic change; flag for EXPLORE
4. If `missing_capability` → propose `replace` to remove the denied claim, OR `append` to document the actual capability

If the same proposed_text already exists in target file → `action: none`, do not duplicate.

## LLM use

If reflect adjustment_points > 5 OR if any prose needs drafting, call LLM. Otherwise the templated proposals are fine.

## Anti-Patterns

- ⛔ Proposing without evidence — every entry must cite reflect.adjustment_points[].evidence
- ⛔ Duplicating existing content — check first
- ⛔ Forcing changes when circuit is correct — empty plan is the most honest output

## Gotchas

| Problem | Root cause | Fix |
|---------|-----------|-----|
| `current_excerpt` not found in file | file changed since absorb | re-absorb or skip this entry |
| Proposed change would create a duplicate | same gate already defined | action: none |
| Change contradicts another gate | gate proliferation | check AGENTS.md for similar gates first |

## Run

```bash
python ~/.hermes/profiles/evol/skills/evol-cycle/phases/adapt/scripts/mismatch_detector.py \
  /tmp/evol_absorb_<target>.json /tmp/evol_reflect_<target>.json \
  -o /tmp/evol_adapt_<target>.json
```

## Evolution Log

| Date | Promotion | Source |
|------|-----------|--------|
| 2026-06-04 | Initial | spec at `references/six-phase-skill-layout.md` |
<!-- last_used: 2026-06-04 -->
