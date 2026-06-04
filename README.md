# hermes-evol — LLM-Driven Evolution

This repository tracks the evolution of all Falke-team agent profiles.

The 6-phase cycle runs as **LLM-driven**, not as a script. The LLM
*inhabits* phases 2 (REFLECT), 3 (EXPRESS), 5 (ADAPT), and the
6-question digest in phase 6. Scripts in `skills/evol-cycle/phases/*/scripts/`
are mechanical helpers (state collection, format validation, diff-check,
garbage stripping) — they do not make interpretive decisions.

## Layout

```
hermes-evol/
├── DEPRECATED.md                       # plugin code is superseded
├── README.md                            # this file
├── skills/
│   ├── evol-cycle/                      # 6-phase cycle infrastructure
│   └── evol-llm-driven-cycle/           # the doctrine: LLM is the cycle
├── profiles/                            # 10 agent circuit files (post-cycle)
│   ├── conductor/
│   ├── analyst/
│   ├── coder/
│   ├── architect/
│   ├── researcher/
│   ├── reviewer/
│   ├── orchestrator/
│   ├── operative/
│   ├── shadow/
│   └── valmet/
├── digests/                             # 10 digests in YAML (target voice)
│   ├── conductor.yaml
│   ├── analyst.yaml
│   └── ...
├── cycles/                              # per-cycle reports
│   └── 2026-06-04-LLM-10-agents/
│       └── CYCLE_REPORT.md
└── hermes_evol/                         # DEPRECATED plugin code
```

## Latest cycle: 2026-06-04 LLM-Driven 10-Agent Evolution

- **20 verified mutations** (2 per agent: SOUL.md + IDENTITY.md)
- **10 digests** (one per agent, all in first-person target voice)
- **0 lies** (all sha-verified, all drift-corrected, all HTML corruption repaired)
- **Common strange attractor:** detection-without-resolution

See `cycles/2026-06-04-LLM-10-agents/CYCLE_REPORT.md` for the full report.
