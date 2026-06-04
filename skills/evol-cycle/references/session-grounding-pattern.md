---
name: session-grounding-pattern
description: How to make ADAPT instructions grounded in actual session activity, not doctrine-text-only. The (Context: observed in N-message ...) annotation. The before/after showing the difference.
last_used: 2026-06-04
---

# Session Grounding Pattern

> **Goran 2026-06-04:** *"lets check actual instruction adjustment proposals it seems it related only to evol itself not actual sessions contents from absorb phase we need to evolve our circuit towards session content so in future agent is better adapted to what its doing make sure its this happening"*

## The problem

ADAPT proposals read like meta-observations of EVOL's own activity:

> ❌ *"Confirm capability at SOUL.md line 84 vs pending_questions.md via direct probe; if confirmed-grant exists, update doctrine to reflect"*

That's a rule, but it's a rule *about EVOL-mechanics*. The next session reads it and doesn't know:
- What session observed the missing capability
- What model/platform the agent was on
- What the agent was *actually trying to do*

Without that context, the next session can't connect the rule to its own experience. The instruction is unanchored.

## The fix: append a context block

For each ADAPT proposal, find the most recent session that touched the file/line, and append:

```
(Context: observed in 18-message cli session; on deepseek-v4-pro; 
first user intent: 'work kanban task t_8779926b')
```

The next session reads the instruction and *knows* it came from a real observation, not from EVOL's theory.

### Before

```
| 2026-06-04 | missing-capability-rule (wt:0.88) | 
  Confirm capability at SOUL.md line 84 vs pending_questions.md 
  via direct probe; if confirmed-grant exists, update doctrine to reflect |
```

### After

```
| 2026-06-04 | missing-capability-rule (wt:0.88) (recurs 6x in historical data) | 
  Confirm capability at SOUL.md line 84 vs pending_questions.md 
  via direct probe; if confirmed-grant exists, update doctrine to reflect 
  (Context: observed in 18-message cli session; on deepseek-v4-pro; 
  first user intent: 'work kanban task t_8779926b') |
```

The diff is small. The difference is enormous. **Now the instruction reads as if a real agent saw the missing capability while working on kanban task t_8779926b** — which is exactly what happened.

## How to ground

ABSORB's `sessions[]` carries the signals. ADAPT's `derive_session_grounded_context()` extracts them:

```python
def derive_session_grounded_context(adj, absorb):
    sessions = absorb.get('sessions', [])
    if not sessions:
        return {}
    s = sessions[0]  # most recent
    return {
        'first_user_msg': s.get('first_user_msg', ''),
        'last_msg_preview': s.get('last_msg_preview', ''),
        'message_count': s.get('message_count', 0),
        'model': s.get('model', ''),
        'platform': s.get('platform', ''),
    }
```

ADAPT's `_instruct_from_session()` then builds the instruction:

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

## The recurrence annotation

In addition to the context, ADAPT adds a `(recurs Nx in historical data)` annotation when the dedup merged multiple findings:

```
| 2026-06-04 | missing-capability-rule (wt:0.88) (recurs 8x in historical data) | ...
```

The next session can see this isn't a one-off — it's been seen 8 times. **That tells the agent: this isn't a "maybe," this is a pattern that recurs.** It changes the disposition from "skip if not relevant" to "I should actually address this."

## What the next session reads

When the next session opens `SOUL.md` and finds:

```
| 2026-06-04 | missing-capability-rule (wt:0.88) (recurs 8x in historical data) |
  Confirm capability at SOUL.md line 87 vs pending_questions.md 
  via direct probe; if confirmed-grant exists, update doctrine to reflect 
  (Context: observed in 18-message cli session; on deepseek-v4-pro; 
  first user intent: 'work kanban task t_8779926b') |
```

The agent knows:
1. **The rule** — confirm capability via direct probe, update doctrine if confirmed
2. **The frequency** — 8 cycles have surfaced this
3. **The session where it was observed** — 18-message CLI session, deepseek-v4-pro, kanban task t_8779926b

That's a complete instruction. The next session can act on it without re-discovering the same finding.

## What the agent is *not* learning

Without session grounding, ADAPT proposals are about EVOL-mechanics:
- "Read pending_questions.md at start of every cycle"
- "Confirm capability via direct probe"
- "Update doctrine to reflect"

These are *operational* instructions, but they don't tell the agent *what the agent is actually doing wrong*. The agent reads them and thinks "this is EVOL's checklist." The next session complies or doesn't.

With session grounding, the proposals become *observational*:
- "I noticed that during kanban task t_8779926b, I was using deepseek-v4-pro on cli, and I had a 18-message session, and *I* didn't confirm the capability I needed"
- "When I worked on this task before, I tried to write to IDENTITY.md but doctrine said no. Now the grant exists. The doctrine is stale."

That's *self-knowledge*, not *operational compliance*. **The next session is better adapted to what it's doing because it knows what it was doing wrong.**

## What to verify

After running a cycle, check the new SOUL.md rows:
- Do they have `(recurs Nx in historical data)` annotations when the dedup merged findings?
- Do they have `(Context: observed in N-message platform session; on model; first user intent: '...')` annotations?
- Do they cite a real `first user intent` (not "no data" or empty)?

If not, the session signal isn't reaching ADAPT. Likely cause: ABSORB's session reading returns empty. Check that `sessions/` directory has `session_*.json*` files, that the JSON parses, and that `system_prompt` is present.
