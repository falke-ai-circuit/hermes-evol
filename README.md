# hermes-evol — Subconscious Observer Plugin for Hermes Agent

A background awareness engine that continuously probes, absorbs, reflects, explores, expresses, and memorizes.

**v0.4.0** — Single source of truth (evol.jsonl), cross-cycle awareness, arXiv integration, multi-gate heartbeat.

## Architecture

```
ABSORB → REFLECT → EXPLORE → EXPRESS → MEMORIZE
  ↑                                       │
  └──────────── evol.jsonl ←──────────────┘
```

Each phase feeds the next. The cycle is a closed loop — what MEMORIZE writes, the next ABSORB reads.

### Phase Mechanics

| Phase | What It Does | LLM Cost | Data Sources |
|-------|-------------|----------|-------------|
| **ABSORB** | Gathers organism state — sessions, circuit files, gateway logs, kanban activity, previous cycle | 0 (mechanical) | JSONL session files, circuit files (SOUL/AGENTS/MEMORY/IDENTITY), evol.jsonl, kanban.db, gateway.log |
| **REFLECT** | Pattern synthesis — finds recurring themes, anomalies, trajectories, bridge paradoxes, knowledge gaps | 1 call (ollama-cloud deepseek-v4-pro) | Absorbed context + previous cycle mood/monologue/unanswered |
| **EXPLORE** | External discovery — web search, arXiv papers, Wikipedia | 2 calls (query formulation + analysis) | DuckDuckGo, arXiv API, Wikipedia, SearXNG, Firecrawl, Google |
| **EXPRESS** | Creative voice — first-person monologue, mood, insights, unanswered questions for next cycle | 1 call (Venice deepseek-v4-pro) | Reflect patterns + explore discoveries + previous monologue |
| **MEMORIZE** | Knowledge persistence — three-tier promotion, cross-cycle pattern detection, circuit file editing | 1 call (ollama-cloud deepseek-v4-pro) | All findings scored against circuit weights, pending proposals auto-applied |

### Heartbeat Triggers (autonomous, every 15 minutes)

| Gate | Trigger | Action |
|------|---------|--------|
| G1 Content | Material buffer ≥ 5 entries | Run REFLECT |
| G2 Activity | Kanban tasks completed since last cycle | Run REFLECT |
| G3 Idle | Last EVOL > 24 hours ago | Run full cycle (guaranteed daily) |
| G4 Express | Reflect completed within past hour | Run EXPRESS |

### Temporal Continuity

Every cycle reads the last `evol.jsonl` entry. Each phase carries forward:
- **Mood** — emotional trajectory across cycles
- **Monologue** — previous voice, referenced in current
- **Unanswered questions** — burning questions that feed next EXPLORE
- **Patterns** — cross-cycle detection surfaces patterns recurring 3+ cycles

### Three-Tier Memory

```
CIRCUIT (SOUL.md · AGENTS.md · IDENTITY.md)  ← promote wt ≥ 0.85
MEMORY.md                                     ← promote wt ≥ 0.65
KNOWLEDGE (~/.hermes/knowledge/)              ← Karpathy wiki, wikilinks
```

Movement: Knowledge → Memory → Circuit (up), Circuit → Memory → Knowledge → deleted (down by decay).

### Provider Routing

| Phase | Provider | Model | Auth |
|-------|----------|-------|------|
| REFLECT | ollama-cloud | deepseek-v4-pro | OLLAMA_API_KEY |
| EXPLORE query | ollama-cloud | deepseek-v4-pro | OLLAMA_API_KEY |
| EXPLORE search | DuckDuckGo / arXiv | — | None |
| EXPRESS | Venice | deepseek-v4-pro | VENICE_API_KEY |
| MEMORIZE | ollama-cloud | deepseek-v4-pro | OLLAMA_API_KEY |

All calls are direct API — zero Hermes gateway dependency.

## Install

```bash
git clone https://github.com/falke-ai-circuit/hermes-evol ~/.hermes/profiles/conductor/plugins/hermes-evol
```

In profile `config.yaml`:
```yaml
plugins:
  enabled:
    - hermes-evol
```

Restart gateway. The heartbeat thread starts automatically.

## Tools

| Tool | Description |
|------|------------|
| `evol_status` | Current state, heartbeat health, material buffer, cooldowns |
| `evol_material` | Accumulated material from absorb ticks |
| `evol_config` | Effective config (mode, edit_mode, phase models) |
| `evol_speak` | Force EXPRESS now (bypasses cooldown) |
| `evol_reflect` | Force REFLECT now (bypasses cooldown) |
| `evol_explore` | Force EXPLORE with optional query |
| `evol_cycle` | Full pipeline: absorb → reflect → explore → express → memorize |

## Slash Commands

```
/evol status              → organism state + EVOL health
/evol material            → material buffer content
/evol config              → effective config
/evol phases              → enable/disable state for all phases
/evol speak               → force inner voice
/evol reflect             → force reflection
/evol explore [query]     → force exploration
/evol cycle               → full pipeline
/evol enable <phase>      → enable a phase
/evol disable <phase>     → disable a phase
```

## Dev

Requires Python 3.11+. Zero external dependencies (stdlib urllib only).

```bash
pip install -e ".[dev]"
pytest tests/
```

## License

MIT — falke-ai-circuit
