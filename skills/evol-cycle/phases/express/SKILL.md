---
name: evol-express
description: Phase 5 of evol-cycle. First-person monologue + surfaced findings to user. Hand-written by default. MUST include surfaced_to_user. No LLM dependency.
last_used: 2026-06-04
---

# EXPRESS — Surface Findings

> Hand-written first-person monologue. **surfaced_to_user is mandatory** — silent cycle = invisible cycle.

## When to load

Load when starting phase 5 of `evol-cycle`. Inputs: reflect + adapt + explore.

## Output contract

```python
{
  "mood": "ice-water clarity after a long confusion",  # or whatever fits
  "insights": ["insight 1", "insight 2", "insight 3"],  # 3-5
  "surfaced_to_user": "the user-facing message; findings go here, not in jsonl",
  "questions": ["unanswered question 1"],
  "voice": "hand"  # or "llm" if LLM was used
}
```

## Algorithm (no LLM by default)

1. **mood**: derive from reflect.anomalies count + clusters count. More anomalies → more sober. Empty plan → "quiet clarity."
2. **insights**: pick the top 3-5 reflect.clusters or adjustment_points, rephrase in plain language.
3. **surfaced_to_user**: this is the message that goes to Goran (or the calling agent). It includes:
   - 1-2 sentence summary of what was found
   - List of proposed changes (from ADAPT plan)
   - The pending_questions status (queued, answered, etc.)
   - The top 1-2 unanswered questions
4. **questions**: reflect.gaps minus what was answered by EXPLORE.

## LLM use

Only if you want a longer, more literary monologue. Default is hand-written, terse, honest.

## Anti-Patterns

- ⛔ Empty `surfaced_to_user` — cycle is invisible. Forbidden.
- ⛔ Only technical jargon — user needs to understand the impact.
- ⛔ Skipping mood — it's the most honest part.

## Gotchas

| Problem | Root cause | Fix |
|---------|-----------|-----|
| surfaced_to_user is too long | tried to include full plan | keep under 500 words; full plan in jsonl |
| surfaced_to_user omits pending_questions | forgot to check explore output | always include pending_questions status |
| Insights are just renamed patterns | no synthesis | rephrase in plain language, not pattern-name |

## Run

```bash
python ~/.hermes/profiles/evol/skills/evol-cycle/phases/express/scripts/monologue.py \
  /tmp/evol_absorb_<target>.json /tmp/evol_reflect_<target>.json \
  /tmp/evol_adapt_<target>.json /tmp/evol_explore_<target>.json \
  -o /tmp/evol_express_<target>.json
```

## Evolution Log

| Date | Promotion | Source |
|------|-----------|--------|
| 2026-06-04 | Initial | spec at `references/six-phase-skill-layout.md` |
<!-- last_used: 2026-06-04 -->
