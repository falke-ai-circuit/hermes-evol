---
name: absorb-substrate-recipe
description: The substrate-building doctrine for ABSORB. Why ABSORB is more than "read state" and how to build the substrate that REFLECT and ADAPT need.
last_used: 2026-06-04
---

# ABSORB Substrate Recipe

> **Goran 2026-06-04:** *"absorb should create a base for reflect ffs so absorb reads agent files ad its sessions from last evol or last session file or whatever"*

## Why ABSORB matters more than it looks

ABSORB is the foundation everything else builds on. If ABSORB reads only the current `evol.jsonl` and stops there, REFLECT gets 0 patterns and ADAPT gets 0 mutations. The cycle runs in 0.5 seconds, prints "verified: 0, skipped: 0", and exits clean. **That is a ceremonial cycle**, not evolution.

**Before/after on conductor:**

| Field | Before substrate | After substrate |
|---|---|---|
| `evol_entries` | 0 | 87 (current + 86 historical) |
| `sessions` | 0 (just metadata) | 50 sessions, 11,143 messages |
| `pending_questions` | 0 | 1 |
| `doctrine_claims` | 0 | 25 |
| `temporal_doctrine` | none | series of 20, drift=216 |
| REFLECT patterns | **0** | **141** |
| REFLECT adjustments | **0** | **2** |
| MEMORIZE mutations | **0 new instructions** | **2 verified instructions** |

The substrate is the difference between a cycle that runs and a cycle that *evolves*.

## What goes in the substrate

| Field | Source | Used by | What it enables |
|---|---|---|---|
| `identity_frontmatter` | parse `---...---` block in IDENTITY.md | REFLECT (anchor) | "the agent is at reflect_count=N today" |
| `circuit_files[*].content` | full read of all 4 circuit files (100k cap) | REFLECT, ADAPT | stale-doctrine detection, §-section extraction, miss-format row detection |
| `doctrine_claims` | extract § sections + "must not/cannot" lines | REFLECT | detect doctrine that contradicts newer grants |
| `evol_entries` (current + historical) | merge `evol.jsonl` + `evol.jsonl.historical-*` | REFLECT | pattern recurrence across cycles (45 patterns on conductor) |
| `sessions[]` (50 most recent) | parse each `session_*.json*` | ADAPT | ground instructions in `(Context: observed in N-message platform session; on model; first user intent: '...')` |
| `temporal_doctrine` | parse system_prompt frontmatter across sessions | ADAPT | detect IDENTITY.md drift; propose replacement |
| `pending_questions` (structured) | parse `## TIMESTAMP (origin)` sections | REFLECT | missing_capability detection |
| `activity` | aggregate from sessions | REFLECT, EXPRESS | detect dormant profiles |

## How to build it (steps)

1. Resolve profiles root via `HERMES_CONFIG_DIR > HERMES_DATA > ~/.hermes/profiles > ~/config_root/profiles` (existence check the default).
2. Read all 4 circuit files fully (100k char cap). Store as `content` (not just `excerpt`).
3. Parse IDENTITY.md frontmatter: `---\nrole: X\nlast_reflect: YYYY-MM-DD\nreflect_count: N\n---` → `identity_frontmatter`.
4. Glob `evol.jsonl.historical-*` and merge with current `evol.jsonl`, flagging historical with `untrusted: true`. Sort by ts (coerce string to float).
5. Glob `sessions/session_*.json*`, sort by mtime desc, take 50 most recent. For each: extract `session_id`, `session_start`, `last_updated`, `platform`, `model`, `message_count`, `role_counts`, `system_prompt_chars`, count `doctrine_hints` (regex on system_prompt), parse frontmatter from system_prompt, capture `first_user_msg` and `last_msg_preview` (first 200 chars).
6. Parse `pending_questions.md` into `[{ts, origin, content}, ...]`.
7. Extract `doctrine_claims`: § sections from MEMORY.md, "must not/cannot" lines from any file.
8. Build `temporal_doctrine.series` from session frontmatters; compute `drift = series[-1].reflect_count - current.reflect_count`.
9. Aggregate `activity` from sessions.

## What NOT to do

- ⛔ **Cap circuit content at 200 lines** — REFLECT needs the full doctrine to find stale claims and miss-format rows. 100k chars is fine.
- ⛔ **Read only session metadata** — without `first_user_msg` / `last_msg_preview` / `frontmatter`, ADAPT has nothing to ground instructions in. The session signal is what makes the next session's instructions read like "I observed this" instead of "EVOL has a theory."
- ⛔ **Skip historical entries** — if `evol.jsonl` was reset, the historical file is the only data source. The merge flag (`untrusted: true`) is what keeps it honest.
- ⛔ **String-sort ts without coercion** — historical entries from quarantine import may have `ts` as a string. `lambda e: e.get('ts', 0) or 0` crashes on that. Use `try: return float(v); except: return 0.0`.
- ⛔ **Default to `~/config_root/profiles/`** without checking existence — that path doesn't exist on this host (the `hermes` user's home is `/opt/data`, not `~`). The chain is existence-checked; the fallback is `~/config_root/profiles` only if nothing else exists.

## Bug history

- **2026-06-04 (caught in 1st run):** `lambda e: e.get('ts', 0) or 0` crashed with `TypeError: '<' not supported between instances of 'str' and 'float'`. Historical entries had string `ts` from the quarantine import. Fixed with `try: return float(v); except: return 0.0`.
- **2026-06-04 (caught in 1st run):** `_lib.profile_dir()` returned `/opt/data/config_root/profiles/{agent}` which doesn't exist on this host. Fixed: chain `HERMES_CONFIG_DIR > HERMES_DATA > ~/.hermes/profiles > ~/config_root/profiles`, with existence check on the `~/.hermes/profiles` default.
- **2026-06-04 (caught in 2nd run):** Substrate read only `size`/`mtime` from sessions, no content. ADAPT proposals were generic ("Read pending_questions.md..."). Fixed: parse `first_user_msg`, `last_msg_preview`, `frontmatter` from system_prompt, store all of it in `sessions[]`.

## Test it

Run the cycle on analyst and conductor. The before/after is the strongest signal. If REFLECT surfaces < 5 patterns on a profile with 50+ sessions and 80+ evol entries, the substrate is too thin.
