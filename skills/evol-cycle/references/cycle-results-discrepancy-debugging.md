---
name: cycle-results-discrepancy-debugging
description: The diagnostic recipe for cycles that "succeed" but produce nothing meaningful. The bash one-liners, the dataflow trace, the "Top patterns: ." bug.
last_used: 2026-06-04
---

# Cycle-Results Discrepancy Debugging

> **Symptom:** The cycle runs in <2s, prints "verified: 0, skipped: 0", exits 0. The user pushes back: *"wtf did this cycle do"*.
>
> The cycle isn't broken. The cycle found nothing to do, because its input is empty. This recipe is for diagnosing which phase's input was empty.

## Quick diagnostic

After a cycle runs, check the four intermediate outputs:

```bash
# Run cycle
SEARXNG_URL=http://100.78.148.26:8080 bash ~/.hermes/profiles/evol/skills/evol-cycle/run.sh <agent>

# Check each phase
for phase in absorb reflect express explore adapt memorize; do
  f=/tmp/evol_${phase}_<agent>.json
  if [ -s "$f" ]; then
    echo "$phase: $(stat -c %s $f) bytes"
  else
    echo "$phase: MISSING OR EMPTY"
  fi
done
```

If any phase is missing, the chain broke. Common cause: a script exited 0 but wrote nothing, or wrote to a different path than the chain expected.

## Dataflow check

The cycle's dataflow is:

```
ABSORB  →  {profile, circuit_files, evol_entries, sessions, temporal_doctrine}
        ↓
REFLECT  →  {patterns, clusters, adjustment_points, anomalies, gaps}
        ↓
EXPRESS  →  {voice, opinion, gap_vector_for_explore, surfaced_to_user}
        ↓
EXPLORE  →  {external, agent_perspective, unanswered}
        ↓
ADAPT    →  {adjustment_plan, actionable, skipped, summary}
        ↓
MEMORIZE →  {verified_mutations, demotions, skipped, jsonl_entry}
```

If REFLECT shows 0 patterns, the issue is upstream. Check:

| Reflect patterns | Likely cause |
|---|---|
| 0 | `evol.jsonl` was reset, no historical merged |
| 0 | sessions directory empty or unreadable |
| < 5 | `doctrine_claims` empty, no reflect findings possible |
| > 5 but adjustments=0 | stale-doctrine / missing-capability checks failed |

If ADAPT shows 0 actionable, the issue is reflect. If MEMORIZE shows 0 verified, the issue is adapt (proposals failed format validation) or the file system.

## The "Top patterns: ." bug

**Symptom:** Express output says `Top patterns: .` (empty list).

**Cause:** Patterns list was empty when express built the opinion. The express script joined the patterns with `, ` and got an empty string.

**Fix:** Handle empty patterns explicitly. The express opinion should say "no patterns surfaced" not show `Top patterns: .`.

## The "0 verified, 0 skipped" bug

**Symptom:** Cycle reports `verified: 0, skipped: 0`.

**Cause:** ADAPT plan was empty, so MEMORIZE had nothing to apply. Run a "deeper" cycle on the same agent and check if ADAPT shows `actionable: 0` — that's the real issue.

**Recovery:** The cycle is correct. The agent's circuit is already correct, or absorb was too thin to surface findings. Check absorb's `evol_entries_count`, `sessions_count_read`, `temporal_doctrine.drift`.

## The "many duplicates" bug

**Symptom:** ADAPT shows 28 actionable but MEMORIZE writes only 5.

**Cause:** Dedup not applied. Each adjustment_point generates a separate proposal, even when they refer to the same (kind, file, line). 

**Recovery:** Check `mismatch_detector.dedupe_adjustment_points()` is called before `propose_for_adjustment()`. The output should show `(recurs Nx in historical data)` annotation in proposals.

## The "garbage 0 but file is full of malformed rows" bug

**Symptom:** Cleanup reports `0 garbage lines` but the file has rows spanning multiple lines.

**Cause:** Line-level pattern doesn't match multi-line rows. The malformed rows have newlines in the action column, so the first line doesn't end with `|`.

**Recovery:** Check `_lib.find_garbage_rows_in_text()` is called. This is a row-level detector that walks line-by-line and finds rows that don't terminate with `|` on the same line.

## The "excerpt_not_found" bug

**Symptom:** MEMORIZE reports `skipped: [{reason: excerpt_not_found}]`.

**Cause:** ADAPT proposed a `replace` action but the `current_excerpt` doesn't match the actual file content. The file changed between ABSORB and MEMORIZE, or ADAPT generated the wrong excerpt.

**Recovery:** Re-absorb (so current_excerpt matches the latest file state), or change the proposal to `append` instead of `replace`.

## The "drift not detected" bug

**Symptom:** IDENTITY.md has stale `reflect_count` (e.g. says 3, sessions show 219) but the cycle doesn't propose a fix.

**Cause:** Either (a) `temporal_doctrine.drift` isn't being computed, (b) ADAPT's `build_temporal_drift_proposal` isn't being called, or (c) the proposal is generated but `excerpt_not_found` on replace.

**Recovery:** Check absorb's `temporal_doctrine.series` is populated, check ADAPT's `drift_proposal` is in the plan, and check the `current_excerpt` matches IDENTITY.md's actual frontmatter.

## Reporting template

When a cycle produces thin output and the user asks "wtf did this do":

> Cycle on {agent}: ran all 6 phases in {N}s.
> - Absorb: {N} evol entries, {N} sessions, drift={N}
> - Reflect: {N} patterns, {N} adjustments
> - Express: voice={ev_proxy|subagent|hybrid}, gap_vector={N} queries
> - Explore: {N} external hits, {status} on agent perspective
> - Adapt: {N} actionable, {N} skipped
> - Memorize: {N} verified mutations, {N} skipped
> - Cleanup: {N} garbage lines stripped
> 
> **The cycle found {summary}:** {one-sentence reason for the result}.

This gives the user a way to see *why* the cycle produced what it produced, not just a count of mutations.

## When the cycle is just thin

If REFLECT shows 0 patterns because the substrate is too thin, the cycle is *correct* but not *useful*. The substrate must reach beyond the current cycle:
- Read `evol.jsonl.historical-*` (merge with `untrusted: true`)
- Read session files for content, not just metadata
- Build `temporal_doctrine` from session frontmatters
- Parse `pending_questions.md` into structured form

See `references/absorb-substrate-recipe.md` for the full substrate-building recipe.
