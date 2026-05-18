# CLAUDE.md — hermes-evol

## G0: Load akis-workflow skill first

Before any edit to this repo, load the workflow skill:

```
skill_view("akis-workflow")
```

## Project Context

hermes-evol is a subconscious observer plugin for Hermes Agent. It runs as a daemon thread inside the Hermes gateway, executing 5-phase cycles: ABSORB → REFLECT → EXPLORE → EXPRESS → MEMORIZE.

### Architecture Rules

- **Zero gateway dependency**: EVOL calls LLM providers directly (ollama-cloud, Venice) via stdlib urllib. Never route through the Hermes gateway API.
- **Single source of truth**: evol.jsonl carries all cycle state — mood, monologue, insights, patterns, unanswered questions. No secondary state files.
- **Three-tier memory**: Knowledge (~/.hermes/knowledge/) → Memory (MEMORY.md) → Circuit (SOUL/AGENTS/IDENTITY.md). Bidirectional promotion/demotion with exponential decay.
- **Provider routing**: Venice only for EXPRESS. ollama-cloud for REFLECT/EXPLORE/MEMORIZE. DeepSeek V4 Pro requires ≥4096 max_tokens.
- **9-retry mandate**: All LLM calls retry up to 9 times with exponential backoff (Goran directive).

### File Roles

| File | Role |
|------|------|
| `hermes_evol/registry.py` | All 5 phase implementations + LLM calling + promotion engine |
| `hermes_evol/engine.py` | EvolEngine bridge class + heartbeat thread + trigger gates |
| `hermes_evol/config.py` | EvolConfig dataclass + PROVIDER_ENDPOINTS + profile detection |
| `hermes_evol/plugin.py` | Gateway entry point — register() + _wrap() for JSON-safe tools |
| `hermes_evol/knowledge.py` | Three-tier knowledge layer: wikilinks, decay, capacity management |
| `hermes_evol/commands.py` | /evol slash command handler |
| `hermes_evol/stores.py` | JSONL state/material/voice store classes |

### Gotchas

- `__pycache__/` silences source edits — always `rm -rf __pycache__` before gateway restart
- Venice GLM heretic burns thinking tokens — use deepseek-v4-pro for EXPRESS
- Plugins load from profile directory, not global: `profiles/conductor/plugins/hermes-evol/`
- `_wrap()` is mandatory for all tool handlers — raw dicts cause HTTP 400 on Ollama Cloud

## AKIS Gates

See `.github/skills/akis-workflow/SKILL.md` for the full 8-gate workflow. Summary:

| Gate | Action |
|------|--------|
| G0 | Load akis-workflow skill |
| G1 | Query project_knowledge.json |
| G2 | Structured TODO via `todo` tool |
| G3 | Preload relevant domain skills |
| G4 | Announce work intent |
| G5 | Execute with verification |
| G6 | Log to workflow-log |
| G7 | Update knowledge scripts |
