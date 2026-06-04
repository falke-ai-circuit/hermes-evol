---
name: adapt-three-voice-integration
description: The integration-of-three-voices doctrine for ADAPT. Why ADAPT needs reflect + express + explore, not just reflect. The dedup rule, session grounding, and tier transitions.
last_used: 2026-06-04
---

# ADAPT Three-Voice Integration

> **Goran 2026-06-04:** *"adapt when proposing edits on circuit is respecting circuit editing and understands those are agent instructions and agent will use them as its dna"*

## Why ADAPT needs three voices, not one

The old flow (1-phase adapt after reflect) wrote proposals based on the system's view alone. The result: 36 cycles of proposals that read like *meta-observations of self*, not instructions the agent could actually use. The 5 new inputs are:

| Input | Source | What it adds |
|---|---|---|
| `reflect.adjustment_points` | REFLECT output | what the system sees (pattern recurrence, doctrine staleness) |
| `express.opinion` + `voice` | EXPRESS output | what the *agent itself* would say if asked |
| `explore.external` | EXPLORE output | what the outside world says (SearXNG results, docs) |
| `absorb.temporal_doctrine` | ABSORB output | when IDENTITY.md is stale relative to session reality |
| `absorb.sessions[]` | ABSORB output | what the agent was *actually doing* (first user msg, last preview, model, platform) |

ADAPT integrates all five. The 3-voice doctrine means the proposal is grounded in:
1. **What the system sees** (reflect)
2. **What the agent would want** (express)
3. **What's actually true outside** (explore)

## The dedup rule

**Bug (caught 2026-06-04):** A single missing_capability finding across 5 lines of doctrine produced **28 proposals** (5 unique × 5-7x). The dedup at MEMORIZE caught the duplicates (25 of 28 skipped), but ADAPT shouldn't have generated 28 in the first place.

**Fix:** Collapse `adjustment_points` by `(kind, file, line)` before generating proposals:

```python
def dedupe_adjustment_points(adjustment_points: list) -> list:
    by_key = {}
    for ap in adjustment_points:
        # Parse (file, line) from "SOUL.md line 84 vs pending_questions.md"
        where = ap.get('where', '').split(' vs ')[0]
        parts = where.rsplit(' line ', 1)
        if len(parts) == 2:
            file_part, line_part = parts
            line_num = int(line_part.strip().split()[0])  # 0 if NaN
        else:
            file_part, line_num = where, 0
        key = (ap.get('kind', ''), file_part.strip(), line_num)
        if key not in by_key:
            by_key[key] = ap.copy()
            by_key[key]['_merged_count'] = 1
        else:
            # Keep higher weight, merge evidence, increment merge count
            existing = by_key[key]
            if ap.get('weight', 0) > existing.get('weight', 0):
                existing['weight'] = ap.get('weight', 0)
            existing['_merged_count'] = existing.get('_merged_count', 1) + 1
    return list(by_key.values())
```

After dedup, the merged proposal carries `_merged_count > 1`, and the proposal text gets a `(recurs Nx in historical data)` annotation. The next session can see *this isn't a one-off* — it's been seen N times.

## Session grounding

**Bug (caught 2026-06-04):** Proposals read like EVOL's self-referential observations: *"Confirm capability at SOUL.md line 84 vs pending_questions.md via direct probe; if confirmed-grant exists, update doctrine to reflect"*. That's a rule, but it's a rule *about EVOL-mechanics*, not about what the agent is actually doing.

**Fix:** Before generating the proposal, find the most recent session that touched the file/line, and append a context block to the instruction:

```python
def _instruct_from_session(kind, evidence, where, session_signal):
    base = _instruct_from(kind, evidence, where)
    if not session_signal:
        return base
    grounding = []
    if msg := session_signal.get('message_count'):
        grounding.append(f"observed in {msg}-message {session_signal.get('platform','')} session")
    if model := session_signal.get('model'):
        grounding.append(f"on {model}")
    if first := session_signal.get('first_user_msg'):
        grounding.append(f"first user intent: '{first[:60]}'")
    if last := session_signal.get('last_msg_preview'):
        grounding.append(f"last state: '{last[:60]}'")
    if not grounding:
        return base
    return f"{base} (Context: {'; '.join(grounding[:3])})"
```

The output now reads:
```
| 2026-06-04 | missing-capability-rule (wt:0.88) (recurs 8x in historical data) |
  Confirm capability at SOUL.md line 87 vs pending_questions.md 
  via direct probe; if confirmed-grant exists, update doctrine to reflect 
  (Context: observed in 18-message cli session; on deepseek-v4-pro; 
  first user intent: 'work kanban task t_8779926b') |
```

The instruction is now grounded in *real activity*, not self-referential observation. **This is the difference between evolution that the next session can use, and evolution that's just more meta-commentary.**

## Tier transitions (not just append)

ADAPT proposals specify tier transitions explicitly:

| Action | Tier | What it means |
|---|---|---|
| `append` to SOUL/AGENTS/IDENTITY | `CIRCUIT` (weight ≥ 0.85) | Promote to durable doctrine. Must be a real instruction. |
| `append` to MEMORY.md | `MEMORY` (weight ≥ 0.65) | Working memory. Same format rules. |
| `append_demotion_marker` to MEMORY.md | `KNOWLEDGE` (weight < 0.35) | Demote from circuit. Tag with `demoted-{name}`. |
| `replace` on IDENTITY.md | `CIRCUIT` | Drift correction. Only when `temporal_doctrine.drift > 0`. |
| `cleanup` on circuit files | `KNOWLEDGE` | Strip CROSS-CYCLE PATTERN spam + multi-line garbage rows. |

The `_lib.classify_tier(weight)` helper maps weight to tier:

| Weight | Tier |
|---|---|
| ≥ 0.85 | CIRCUIT |
| 0.65–0.85 | MEMORY |
| 0.35–0.65 | KNOWLEDGE |
| < 0.35 | decay (skip) |

## Conflict resolution rule

**3-way conflict (reflect vs express vs explore) → escalate to user, do not auto-resolve.**

**2-way (both confirm) → trust the proposal. Both contradict → auto-demote. Otherwise, leave as-is.**

```python
def apply_conflict_rules(plan, express, explore):
    opinion = (express.get('opinion') or '').lower()
    external_text = ' '.join(e.get('snippet','').lower() + e.get('title','').lower()
                             for e in explore.get('external', []))
    for p in plan:
        ev = (p.get('evidence') or '').lower()
        opinion_disagrees = ('fine' in opinion or 'correct' in opinion or 'not stale' in opinion) and ('stale' in ev or 'wrong' in ev or 'broken' in ev)
        external_disagrees = 'no evidence' in external_text and ('stale' in ev or 'broken' in ev)
        if opinion_disagrees and external_disagrees:
            p['action'] = 'demote_to_knowledge'
            p['demotion_reason'] = 'agent + external both contradict reflect finding'
        elif opinion_disagrees or external_disagrees:
            p['action'] = 'none'
            p['skip_reason'] = 'partial contradiction — escalate'
    return plan
```

## Format: action is in the proposal, not in MEMORIZE

MEMORIZE should not have to guess what an item means. The ADAPT proposal carries:

```python
{
  "file": "SOUL.md",             # or "AGENTS.md", "MEMORY.md", "IDENTITY.md", "ALL" for cleanup
  "tier": "CIRCUIT",             # CIRCUIT / MEMORY / KNOWLEDGE / decay
  "action": "append",            # append | replace | cleanup | append_demotion_marker | demote_to_knowledge | none
  "current_excerpt": "...",      # for replace: exact text to find (None for append)
  "proposed_text": "...",        # the actual instruction (not metadata)
  "evidence": "...",             # from reflect + session signal
  "weight": 0.88,                # from reflect
  "instruction_format": "soul_evolution_log_row"  # the file's required format
}
```

The `instruction_format` must match the file's format spec. See `references/actionable-instruction-principle.md` for the validator and format rules.

## Temporal drift detection (the IDENTITY.md fix)

**Bug (caught 2026-06-04):** IDENTITY.md's `reflect_count: 3` was 213 cycles behind the actual session reality (most recent system_prompt says `reflect_count: 219`). The cycle wasn't catching this.

**Fix:** ABSORB builds `temporal_doctrine.series` from session frontmatters. ADAPT compares `series[-1].reflect_count` to `current.reflect_count` (from IDENTITY.md). If `drift > 0`, propose a `replace` on IDENTITY.md's frontmatter:

```python
def build_temporal_drift_proposal(temporal, target):
    drift = temporal.get('drift', 0)
    if drift <= 0:
        return {"action": "none", "reason": "no_drift_to_heal"}
    current = temporal.get('current', {})
    series = temporal.get('series', [])
    actual_count = max(current.get('reflect_count', 0), series[-1].get('reflect_count', 0))
    today = datetime.now().strftime('%Y-%m-%d')
    return {
        "file": "IDENTITY.md",
        "tier": "CIRCUIT",
        "action": "replace",
        "current_excerpt": f"---\nrole: {current.get('role', target)}\nlast_reflect: {current.get('last_reflect', '')}\nreflect_count: {current.get('reflect_count', 0)}\n---",
        "proposed_text": f"---\nrole: {current.get('role', target)}\nlast_reflect: {today}\nreflect_count: {actual_count}\n---",
        "evidence": f"Drift detected: IDENTITY.md says reflect_count={current.get('reflect_count', 0)}, "
                    f"most recent session's system_prompt says reflect_count={series[-1].get('reflect_count', 0)}. "
                    f"Drift of {drift} cycles unaccounted for.",
        "weight": 0.95,
        "instruction_format": "identity_frontmatter_replacement",
        "drift_magnitude": drift,
    }
```

## Test it

Run the cycle on a profile with many sessions (conductor has 800+). ADAPT should produce proposals that:
- Are deduplicated (one per unique `(kind, file, line)`, not 28 copies of the same finding)
- Have `_merged_count` annotation when proposals were merged
- Have `(Context: observed in ...)` appended to ground them in session reality
- Include IDENTITY.md drift correction when temporal_doctrine.drift > 0
- Use `_instruct_from()` translation, never the raw `evidence` text
