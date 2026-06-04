# DEPRECATED — Plugin Code Superseded

The Python plugin code in `hermes_evol/` and the `skills/evol/scripts/hooks/`
hooks are **DEPRECATED** as of 2026-06-04.

## What replaced it

The LLM-driven 6-phase cycle now lives in skills:

- `skills/evol-cycle/` — the 6-phase cycle infrastructure (run.sh + phases scripts)
- `skills/evol-llm-driven-cycle/` — the doctrine: phases 2, 3, 5, and the digest are LLM-interpretive; scripts assist but do not decide

The plugin (`hermes_evol/`) is no longer called. The `evol_` toolset is
disabled in all 11 profile configs. The cycle runs as a direct `bash
skills/evol-cycle/run.sh {agent}` invocation, with phases 2, 3, 5, and
the digest performed by the LLM.

## Why

Three reasons:

1. The plugin's `applied: true` field was untrustworthy (lying log — see
   digests for the documentation).
2. The 5-phase plugin had no concept of interpretive phases; the LLM
   cycle does.
3. The 6-question digest is a new artifact that the plugin never produced.

## Migration

For each agent that needs evolution:

```bash
# Mechanical phases 1, 4, 6 (and partial of 5: format validation, dedup)
bash skills/evol-cycle/run.sh {agent}

# LLM-driven phases 2, 3, 5, and the digest:
#   1. Load skill_view(name='evol-llm-driven-cycle')
#   2. Read target's circuit files
#   3. Reason through phases 2, 3, 5 as the LLM
#   4. Write 6-question digest in target agent's voice
#   5. Append to {agent}/evol.jsonl
```

## What is preserved

- The plugin's tests pass and the code compiles. We are not deleting the
  plugin — we are noting its deprecation.
- Future cycles may revive the plugin for specific automation use cases
  (e.g., bulk profile audits), but the LLM-driven cycle is the default.
