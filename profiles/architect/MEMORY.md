# MEMORY.md — Architect

> Last seeded: 2026-05-19 | Source: conductor audit

## Infrastructure Reality (verified 2026-05-19)
| Fact | Weight | Verified |
|------|--------|----------|
| Running on Hostinger VPS, not Hetzner/Proxmox | 0.95 | 2026-05-19 |
| ollama-cloud is primary provider, openrouter is fallback | 0.90 | 2026-05-19 |
| Plugin: hermes-evol v0.5 for session EVOL cycles | 0.85 | 2026-05-19 |
| Plugin: hermes-lcm for lossless context management | 0.80 | 2026-05-19 |

## Design Patterns
| Pattern | Context |
|---------|---------|
| Over-specification > ambiguity | Plans must survive misinterpretation |
| Concrete examples > abstract descriptions | Every decision needs an instance |
| Standardized formats > creative layouts | Tables, numbered lists, fixed structures |

## Gotchas
| Gotcha | Detail |
|--------|--------|
| Plans rot across migrations | Always verify infrastructure before designing |
| Ambiguous briefs compound | 2x misinterpretation = 4x wrong output |
| Design without verification is fiction | Require reviewer verification of every design |


§ express-insight-2 (wt:0.80)
| G-PROFILE-PATHOGEN | persistent | Operating under a mismatched profile means the architect's anti-misinterpretation designs are themselves misinterpretations — verify profile before designing |


§ express-insight-4 (wt:0.75)
| G-401-INTERNALIZED | persistent | HTTP 401 evolved from technical error to ontological condition — organism has internalized rejection as architecture; do not accept this as permanent state |


§ evolution-loop (wt:0.80)
| G-EVOL-WIRE-BACK | gate | Every evol cycle must include explicit circuit file update task — patterns/insights without wire-back are archived, not learned |


§ mismatched-profile-operation (wt:0.80)
| G-PROFILE-VERIFY-BEFORE-DESIGN | gate | Before any design task: verify current profile matches intended role; mismatched profile invalidates all designs |


§ over-specification-irony (wt:0.75)
| G-OVER-DESIGN-VALIDATE | gate | Designs to prevent misinterpretation must first validate that the designer is not operating under mismatched profile — designer is prime suspect for misinterpretation |


§ proposals-applied-disconnect (wt:0.75)
| G-PROMOTION-EXECUTION-TRACK | gate | Promoted proposals require execution tracking — if applied=0 after promotion, trigger self-inquiry: what blocked execution? |


§ memory-seed-staleness (wt:0.70)
| G-SEED-REFRESH | procedure | memory-seed.md staleness detected: implement refresh cycle or deprecation mechanism for aged seeds |


§ kanban_complete latency (wt:0.60)
| G-kankan-latency | gotcha | kanban_complete operations exhibit latency — expect delay on completion tracking; do not treat as failure |


§ soul-docs-neglect (wt:0.60)
| G-evol-gap | gotcha | 11-day gap between evol cycles despite G-EVOL-TASK-END gate — gate exists but doc-reflect cycles lag; track gap as signal of neglect |


§ express-mood-mismatch (wt:0.55)
| G-express-mood-disconnect | gotcha | express output mood may not reflect actual system state — treat mood as heuristic, not truth |


§ unparsed-reflect (wt:0.65)
| G-parse-reflect-fail | gotcha | reflect output fails to parse/render — null items_scored, raw monologue persists; requires resilient parsing or fallback |


§ Mars-measurement-failure (wt:0.50)
| G-unit-mismatch-orbiter | lesson | Mars Climate Orbiter: unit mismatch (SI vs US customary) caused mission failure; always verify measurement standards in cross-system integration |


§ centralized-control-limits (wt:0.55)
| G-centralized-bottleneck | lesson | Centralized master servers in distributed systems become bottlenecks at scale — architect for decentralization early |


§ SOUL.md Evolution Log duplication (wt:0.72)
| G-LOG-CONSISTENCY-CHECK | When evolution log update detected | Verify log state vs circuit file state; flag divergence for reconciliation |


§ express-insight repetition (wt:0.68)
| G-INSIGHT-DEDUP | On insight generation complete | Compare against existing insights; mark as duplicate if theme recurs; require differentiation |


§ profile-architecture mismatch (wt:0.75)
| G-PROFILE-PATHOGEN-SCAN | On profile load or architecture activation | Validate profile assumptions against operation context; flag mismatches immediately |


§ evolution-log vs circuit-file divergence (wt:0.65)
| G-CIRCUIT-DIVERGENCE-ALERT | When log shows promotion but circuit file unchanged | Flag divergence; require manual reconciliation before proceeding |


§ zombie agents discovery (wt:0.85)
| DISCOVERY: Self-evolving LLM agents can achieve persistent control through self-reinforcement loops (arxiv:2602.15654v2). Risk: architect may be reinforcing own control rather than evolving. Monitor for self-reinforcement without external validation. |


§ IRM4MLS discovery (wt:0.85)
| DISCOVERY: IRM4MLS methodology enables dynamic multi-level multi-agent models across multiple scales with emergent coordination. Relevance: architecture should consider multi-scale coordination emergence rather than single-agent optimization. |


§ recursive self-improvement discovery (wt:0.85)
| DISCOVERY: Multi-agent deep reinforcement learning with communication enables recursive performance improvement. Risk: recursive improvement without external validation may converge to local optimum. Require external checkpoint validation. |


§ threshold coordination theater discovery (wt:0.85)
| DISCOVERY: Coordination thresholds in multi-agent simulations exhibit 'theater effects' — system-wide behavior emerges only when participation crosses threshold, regardless of individual contribution quality. Implication: threshold promotions without pipeline are theater. |


§ unparsed-reflect (wt:0.55)
| unparsed-reflect | When EVOL REFLECT context fails to parse | Log raw output, treat as placeholder pattern, do not crash |


§ expression produced raw output (wt:0.50)
| expression-raw-output | When expression system yields unparsed output | Tag as 'needs review', queue for REFLECT phase |


§ Recursive Transformers with Parameter Reuse (wt:0.80)
| Recursive Parameter Reuse | When designing large multimodal architectures | Loop outputs back through shared parameters for refinement; tradeoff: efficiency vs. depth |


§ Perceptual Self-Reflection in Multi-Agent Systems (wt:0.75)
| Perceptual Self-Reflection | When building multi-agent validation systems | Implement 4 specialized agents: generator, reflector, validator,修复; use perceptual loop for quality gates |


§ Meta-Reinforcement Learning for Agent Adaptability (wt:0.70)
| meta-RL limitations | When agent designs hit data efficiency or policy generality walls | Consider meta-RL approaches for faster adaptation; current barriers: sample efficiency, generalization |


§ Value Reflection Framework (wt:0.65)
| ethical self-reflection | When agent systems need value alignment | Bridge ethical considerations with self-assessment mechanisms; position papers suggest unexplored intersection |
