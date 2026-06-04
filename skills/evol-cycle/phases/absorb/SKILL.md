---
name: evol-absorb
description: Phase 1 of evol-cycle. Read target agent's circuit files, evol.jsonl, recent sessions, pending_questions, kanban state. No LLM, no writes. Returns a structured state dict.
last_used: 2026-06-04
---

# ABSORB — Read Agent State

> Read-only. No LLM. No writes. Output is a Python dict that the next phases consume.

## When to load

Load when starting phase 1 of `evol-cycle` on a target agent.

## Inputs

- `target_agent` — profile name (e.g. `analyst`, `conductor`)

## Output contract

```python
{
  "profile": "analyst",
  "circuit_files": {
    "SOUL.md":   {"path": "...", "size": 1234, "mtime": 1234567890, "excerpt": "..."},
    "AGENTS.md": {"path": "...", ...},
    "MEMORY.md": {"path": "...", ...},
    "IDENTITY.md": {"path": "...", ...},
  },
  "sessions": [{"id": "session_...", "started_at": ..., "tool_calls": N, "tokens": T}],
  "evol_entries": [{...parsed from evol.jsonl...}],
  "kanban_recent": [...from kanban.db or empty...],
  "last_reflect_ts": 1234567890.0,  # 0 if never
  "pending_questions": [...lines from pending_questions.md...],
  "doctrine_claims": [...key assertions from MEMORY.md/AGENTS.md with line numbers...],
  "falkordb_graphs": [...]  # only if FALKORDB_URL set
}
```

## What to read

1. **Circuit files** — `~/.hermes/profiles/{target}/SOUL.md`, `AGENTS.md`, `MEMORY.md`, `IDENTITY.md`. First 200 lines each.
2. **evol.jsonl** — last 50 entries.
3. **Sessions** — list of `~/.hermes/profiles/{target}/sessions/session_*.json`, sort by mtime desc, take last 10.
4. **Kanban** — `~/.hermes/kanban.db` (read-only) — last 20 tasks involving target.
5. **pending_questions.md** — if exists, all unresolved lines.
6. **Doctrine claims** — extract assertions like "X cannot do Y" or "X is the cause of Z" from MEMORY.md for stale-doctrine check.
7. **FalkorDB** — if `FALKORDB_URL` env var set, `GRAPH.LIST` and counts. Skip otherwise.

## Anti-Patterns

- ⛔ Writing anything — ABSORB is read-only.
- ⛔ Calling LLM — pure file read.
- ⛔ Inventing data — if a file is missing, mark it `missing: true`, don't fabricate.
- ⛔ Reading full files — use limit=200 to keep absorb fast.

## Gotchas

| Problem | Root cause | Fix |
|---------|-----------|-----|
| `pending_questions.md` is huge | Many unanswered over cycles | truncate to last 10, mark `n_total: N` |
| `kanban.db` locked | Another process is writing | retry once with 0.5s sleep, then skip |
| Circuit file is binary / unparseable | corrupted | log `corrupted: true`, skip excerpt |
| evol.jsonl is empty | just reset | return `evol_entries: []` |

## Run

```bash
python ~/.hermes/profiles/evol/skills/evol-cycle/phases/absorb/scripts/collect_state.py <target_agent> \
  > /tmp/evol_absorb_<target>.json
```

## Evolution Log

| Date | Promotion | Source |
|------|-----------|--------|
| 2026-06-04 | Initial | spec at `references/six-phase-skill-layout.md` |
<!-- last_used: 2026-06-04 -->
