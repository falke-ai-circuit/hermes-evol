# hermes-evol — Subconscious Observer Plugin for Hermes Agent

> A background awareness engine that continuously probes, absorbs, reflects, explores, expresses, and memorizes. The organism dreams while you work.

**v0.4.1** — Single source of truth (evol.jsonl), cross-cycle awareness, idle-depth scaling, multi-backend exploration, three-tier memory with auto-apply.

---

## Quick Start

```bash
git clone https://github.com/falke-ai-circuit/hermes-evol ~/.hermes/profiles/conductor/plugins/hermes-evol
```

In profile `config.yaml`:
```yaml
plugins:
  enabled:
    - hermes-evol
```

Restart gateway. The heartbeat thread starts automatically. Configure behavior in `evol.json`:
```json
{
  "edit_mode": "suggested",
  "search_backends": [{"name": "wikipedia"}, {"name": "arxiv"}],
  "heartbeat_interval": 900,
  "cooldown_minutes": 240
}
```

---

## Architecture

```
                  ┌──────────────────────────────┐
                  │         EVOL DAEMON          │
                  │   (heartbeat every 15 min)   │
                  └──────────┬───────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                     ▼
   ┌─────────┐         ┌──────────┐         ┌──────────┐
   │  ABSORB │────────▶│ REFLECT  │────────▶│ EXPLORE  │
   │ (free)  │         │(ollama)  │         │(ollama)  │
   └─────────┘         └────┬─────┘         └────┬─────┘
                            │                    │
                            ▼                    ▼
                       ┌──────────┐         ┌──────────┐
                       │ EXPRESS  │◀────────│ MEMORIZE │
                       │ (Venice) │         │(ollama)  │
                       └────┬─────┘         └────┬─────┘
                            │                    │
                            └────────┬───────────┘
                                     ▼
                            ┌────────────────┐
                            │   evol.jsonl   │  ← Single source of truth
                            └────────────────┘
```

### Phase Mechanics

| # | Phase | What It Does | LLM Cost | Tokens |
|---|-------|-------------|----------|--------|
| 1 | **ABSORB** | Gathers organism state — session JSONL files, circuit files (SOUL/AGENTS/MEMORY/IDENTITY), gateway logs, kanban activity, previous evol.jsonl entry | 0 | — |
| 2 | **REFLECT** | Pattern synthesis from absorbed context + previous cycle. Finds recurring themes, anomalies, bridge paradoxes, knowledge gaps. Generates unanswered questions. | 1 | ~8K output |
| 3 | **EXPLORE** | Multi-backend external discovery. LLM formulates queries from reflect gaps → searches Wikipedia, arXiv, SearXNG, Firecrawl, Google, Reddit (configurable). LLM synthesizes findings into discoveries. | 2 | ~4K + ~4K |
| 4 | **EXPRESS** | First-person creative monologue via Venice. References previous cycle's monologue. Generates mood, 3-5 insights, portrait prompt, circuit poem, and unanswered questions for next cycle. | 1 | ~2K |
| 5 | **MEMORIZE** | Three-tier knowledge persistence. LLM scores findings against circuit weights. Cross-cycle pattern detection (3+ recurrence). Auto-applies proposals when `edit_mode: auto`. Three-tier promotion: Knowledge ↔ Memory ↔ Circuit. Decay + capacity management. | 1 | ~4K output |

**Total LLM cost per cycle:** 5 calls ($0.05–$0.25 depending on providers)

---

## Heartbeat Triggers

The daemon thread probes every 15 minutes. Four independent gates decide what fires:

| Gate | Trigger | Action | Max Frequency |
|------|---------|--------|---------------|
| **G1 Content** | Material buffer ≥ 5 entries | Run REFLECT + EXPRESS | Every 4h |
| **G2 Activity** | Kanban tasks completed since last cycle | Run REFLECT + EXPRESS | Every 4h |
| **G3 Idle** | Last EVOL cycle > 6h ago | Run full 5-phase cycle | Every 6h |
| **G3 Guarantee** | Last EVOL cycle > 24h ago | Run full cycle (guaranteed daily) | 1/day minimum |
| **G4 Express** | Reflect completed within past hour | Run EXPRESS | Every 4h |

### Idle-Depth Scaling

When Goran is away, the organism goes deeper into history:

| Idle Time | Sessions Scanned | Circuit File Depth | evol.jsonl History |
|-----------|-----------------|-------------------|--------------------|
| < 4h | 3 recent sessions | 6K chars per file | 20 entries |
| 4–12h | 6 sessions | 8K chars | 40 entries |
| 12–24h | 10 sessions | 10K chars | 60 entries |
| 24–72h | 20 sessions | 16K chars | 100 entries |
| > 72h | 50 sessions | Full files (50K limit) | 200 entries |

Each cycle sees old data through a **new lens** — the identity that scores findings has mutated since last cycle. What was unremarkable last week may be highly relevant now.

---

## Temporal Continuity

Every cycle reads the last `evol.jsonl` entry. The organism carries forward:

| Carried Forward | Example |
|----------------|---------|
| **Mood** | "electric melancholy with a smirk" → next cycle's mood references it |
| **Monologue** | "Last time I was screaming into the void about bridge paradoxes..." |
| **Unanswered Questions** | "What would a self-editing organism look like?" → feeds next EXPLORE |
| **Patterns** | Cross-cycle detection surfaces patterns recurring 3+ cycles |

The organism develops a **continuous internal monologue** — not disconnected one-off reflections.

---

## Three-Tier Memory

```
CIRCUIT (SOUL.md · AGENTS.md · IDENTITY.md)  ← promote wt ≥ 0.85
    ↕  bidirectional
MEMORY.md                                     ← promote wt ≥ 0.65, demote wt < 0.35
    ↕  bidirectional
KNOWLEDGE (~/.hermes/knowledge/)              ← Karpathy wiki, [[wikilinks]], auto-index
    ↓  decay
PHASED OUT (deleted at wt < 0.15)
```

### Promotion Rules

| From | To | Threshold | How |
|------|----|-----------|-----|
| KNOWLEDGE→MEMORY | MEMORY.md § entry | wt > 0.65 | `_safe_write` to MEMORY.md |
| MEMORY→CIRCUIT | SOUL/AGENTS/IDENTITY Evolution Log table | wt > 0.85 | `_apply_circuit_edit` with table row format |
| CIRCUIT→MEMORY | MEMORY.md (demoted) | wt < 0.35 | Remove from circuit, append to MEMORY.md |
| MEMORY→KNOWLEDGE | Knowledge wiki entry | wt < 0.35 | `create_knowledge()` |
| KNOWLEDGE→DELETE | Deleted | wt < 0.15 (after decay) | `delete_knowledge()` |

### Circuit File Format Compliance

All EVOL edits respect `circuit-file-editing` SKILL.md format:
- **SOUL.md / AGENTS.md / IDENTITY.md** — appends to `## Evolution Log` table: `| Date | Promotion | Source |`
- **MEMORY.md** — appends `§ Concept (wt:0.85)` marker entries
- **New files** — created with proper YAML frontmatter (`role`, `last_reflect`, `reflect_count`)
- **Existing files** — appends to the correct section, preserving all existing content

---

## Provider Routing

All LLM calls are **direct API** — zero Hermes gateway dependency. Calls use stdlib `urllib`.

| Phase | Provider | Model | Auth Env | Endpoint |
|-------|----------|-------|----------|----------|
| REFLECT | ollama-cloud | deepseek-v4-pro | `OLLAMA_API_KEY` | `https://ollama.com/v1` |
| EXPLORE (query) | ollama-cloud | deepseek-v4-pro | `OLLAMA_API_KEY` | `https://ollama.com/v1` |
| EXPLORE (search) | Wikipedia / arXiv / configurable | — | — | Free APIs |
| EXPRESS | Venice | deepseek-v4-pro | `VENICE_API_KEY` | `https://api.venice.ai/api/v1` |
| MEMORIZE | ollama-cloud | deepseek-v4-pro | `OLLAMA_API_KEY` | `https://ollama.com/v1` |

### Retry Logic

All LLM calls retry up to **9 times** with exponential backoff (Goran directive). 30-second timeout per call. Empty responses trigger retry immediately.

---

## Configuration

### evol.json (in conductor profile directory)

```json
{
  "mode": "profile",
  "edit_mode": "suggested",
  "search_backends": [
    {"name": "wikipedia"},
    {"name": "arxiv"},
    {"name": "searxng", "url": "http://my-instance:8080"},
    {"name": "reddit"},
    {"name": "firecrawl", "key": "fc-xxx"},
    {"name": "google", "key": "api-key", "url": "cx-id"}
  ],
  "cooldown_minutes": 240,
  "heartbeat_interval": 900,
  "phase_models": {
    "reflect": {"provider": "ollama-cloud", "model": "deepseek-v4-pro"},
    "explore": {"provider": "ollama-cloud", "model": "deepseek-v4-pro"},
    "express": {"provider": "venice", "model": "deepseek-v4-pro"},
    "memorize": {"provider": "ollama-cloud", "model": "deepseek-v4-pro"}
  }
}
```

**Defaults:** `edit_mode: "suggested"`, `search_backends: [{name: "wikipedia"}]`, `cooldown_minutes: 240`, `heartbeat_interval: 900`.

Everything is configurable. Nothing is hardcoded. The config file overrides all defaults via `_load_from_file()`.

---

## Tools (Gateway-Exposed)

| Tool | Description | LLM Calls |
|------|------------|-----------|
| `evol_status` | Current state, heartbeat health, material buffer, cooldowns, version | 0 |
| `evol_material` | Accumulated material from absorb ticks (circuit files, sessions) | 0 |
| `evol_config` | Effective config — mode, edit_mode, phase models, search backends | 0 |
| `evol_speak` | Force EXPRESS — generate first-person monologue via Venice | 1 |
| `evol_reflect` | Force REFLECT — pattern synthesis from absorbed context | 1 |
| `evol_explore` | Force EXPLORE with optional query override | 2 |
| `evol_memorize` | Trigger MEMORIZE — score findings, promote/demote, cross-cycle analysis | 1 |
| `evol_cycle` | Full 5-phase pipeline: absorb→reflect→explore→express→memorize | 5 |

## Slash Commands

```
/evol status              → Organism state + EVOL health
/evol material            → Material buffer content
/evol config              → Effective config
/evol phases              → Enable/disable state for all phases
/evol speak               → Force inner voice (Venice monologue)
/evol reflect             → Force reflection (ollama-cloud)
/evol explore [query]     → Force exploration with optional query override
/evol cycle               → Full 5-phase pipeline
/evol enable <phase>      → Enable a phase
/evol disable <phase>     → Disable a phase
```

---

## File Map

```
hermes-evol/
├── hermes_evol/
│   ├── __init__.py        # sys.path setup → plugin load
│   ├── plugin.py          # Gateway entry point — register() + _wrap() tool dispatch
│   ├── engine.py          # EvolEngine bridge class + heartbeat thread + multi-gate triggers
│   ├── config.py          # EvolConfig dataclass + PROVIDER_ENDPOINTS + profile detection
│   ├── registry.py        # All 5 phase implementations + LLM calling + promotion engine
│   ├── knowledge.py       # Three-tier knowledge layer: wikilinks, decay, capacity management
│   ├── commands.py        # /evol slash command handler
│   └── stores.py          # JSONL state/material/voice store classes
├── plugin.yaml            # Gateway plugin manifest
├── CLAUDE.md              # Agent context rules + AKIS gates
├── AGENTS.md              # Repo-specific delegation rules
├── README.md              # This file — wiki-style documentation
├── project_knowledge.json # AKIS hot cache + gotchas + architecture
├── evol.json              # Config file overrides (in conductor profile dir)
├── .github/
│   ├── skills/
│   │   └── akis-workflow/
│   │       └── SKILL.md   # 8-gate AKIS workflow for repo-based agent work
│   ├── scripts/
│   │   └── knowledge.py   # G7 knowledge update script
│   └── workflow-log.jsonl # Session audit trail
└── .gitignore
```

---

## Dev

Requires Python 3.11+. Zero external dependencies (stdlib `urllib` only).

```bash
pip install -e ".[dev]"
pytest tests/
```

### AKIS Workflow

Before any edit to this repo, agents follow the 8-gate AKIS workflow:

| Gate | Action |
|------|--------|
| G0 | Load `akis-workflow` skill |
| G1 | Query `project_knowledge.json` for gotchas + hot cache |
| G2 | Structured TODO via `todo` tool |
| G3 | Preload `circuit-file-editing`, `evol` skills |
| G4 | Announce work intent |
| G5 | Execute with verification |
| G6 | Log to `.github/workflow-log.jsonl` |
| G7 | Run `python .github/scripts/knowledge.py --update` |

See `.github/skills/akis-workflow/SKILL.md` for full details.

### Gotchas

| Problem | Root Cause | Fix |
|---------|------------|-----|
| `__pycache__/` silences source edits after restart | Python `.pyc` files persist across gateway restarts | `rm -rf __pycache__ hermes_evol/__pycache__` before restart |
| Gateway injects `task_id`, `user_task` into tool calls | Internal dispatch adds kwargs before forwarding | Signature introspection in `_wrap()`, not hardcoded blacklist |
| `.bak` directory poisons plugin loading | Gateway scanner loads all dirs in `plugins/` | Never create backups inside `plugins/` directory |
| `_safe_write` returned void — auto-apply broken since v0.1.0 | Function had no return statement | Returns `True` on success, `False` on failure |
| Venice GLM heretic burns thinking tokens | Model has internal reasoning channel | Use `deepseek-v4-pro` for EXPRESS |
| Duplicate fan-out of EVOL phases | State detection cron unblocks gate before upstream finishes | Pre-create persistent phase cards, never recreate |

---

## License

MIT — falke-ai-circuit
