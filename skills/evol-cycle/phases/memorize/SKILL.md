---
name: evol-memorize
description: Phase 6 of evol-cycle. Apply ADAPT plan with diff-checked writes. Includes the 6-question digest in target agent's voice. End-of-cycle self-aware narrative.
---
# evol-memorize — Phase 6: MEMORIZE

> Apply the ADAPT plan with diff-checked writes. Includes the post-cycle
> **6-question digest** in the target agent's voice.

## When to load

- `bash skills/evol-cycle/run.sh {target}` has completed phase 5 (ADAPT)
- Or: the LLM is doing a hand-driven cycle and has finished ADAPT

## Mechanical work (script)

The script `phases/memorize/scripts/diff_apply.py` handles:
- Tier transitions (CIRCUIT ≥ 0.85, MEMORY ≥ 0.65, KNOWLEDGE ≥ 0.35)
- Format validation per file (SOUL/IDENTITY = Evolution Log row, AGENTS = Gate
  row, MEMORY = `§ Concept (wt:X.XX)`)
- Diff-checked writes (sha before/after)
- Garbage stripping (CROSS-CYCLE PATTERN spam, malformed rows)
- Demotion markers (when an instruction is superseded)

It does NOT make interpretive decisions. The LLM must approve the final
output and write the digest.

## LLM work (digest)

After `diff_apply.py` runs, the LLM must:

1. **Read the diff_apply output** to know what actually changed
2. **Read the target agent's circuit files** to know the new state
3. **Write the 6-question digest** in first-person, as the target agent
4. **Append the digest to `evol.jsonl`** with the cycle entry
5. **Surface the digest to the user** in the cycle report

### Digest structure

```json
{
  "digest": {
    "q1_was": "...",
    "q2_why_change": "...",
    "q3_discovered": "...",
    "q4_changed": "...",
    "q5_affected": "...",
    "q6_remember": "..."
  }
}
```

The digest is the cycle's self-aware narrative. It is what the agent will
read next time it asks "what happened to me?" The next cycle's REFLECT
phase should use the digest as part of its substrate.

## Anti-pattern (DO NOT)

- Skip the digest. The cycle is not complete without it.
- Write the digest in EVOL's voice. It must be the target agent's voice.
- Use the digest to claim the cycle is successful. Verify the diffs first.
- Forget to append the digest to `evol.jsonl`. Future cycles need it.

## Before writing the digest: saturation check

The digest should *acknowledge* the cycle's own state. If the last 3+
cycles have skip rate > 50% AND monotonically non-decreasing, the
circuit is saturated, and the digest's Q3 ("what did I discover") and
Q6 ("what will I remember") should *both* address the saturation. The
cycle is not just changing the agent — it is noticing that it keeps
changing the agent in the same way. See
`evol-core/references/cycle-saturation-and-digest-doctrine.md` for
the full saturation-response playbook.
