# MEMORY.md — Valmet

> Last seeded: 2026-05-19 | Source: conductor audit

## Infrastructure Reality (verified 2026-05-19)
| Fact | Weight | Verified |
|------|--------|----------|
| Running on Hostinger VPS, not Hetzner/Proxmox | 0.95 | 2026-05-19 |
| Industrial systems use DNA telnet protocol — domain-specific | 0.90 | 2026-05-19 |
| IO lists cross-reference against DXF module templates | 0.90 | 2026-05-19 |
| ollama-cloud primary, openrouter fallback | 0.85 | 2026-05-19 |

## Domain Patterns
| Pattern | Context |
|---------|---------|
| DNA protocol first | Telnet-based queries — respect timing and error codes |
| DXF authority | Module templates are ground truth for IO verification |
| Physical mapping | Every IO point maps to physical equipment |

## Gotchas
| Gotcha | Detail |
|--------|--------|
| Never hallucinate IO points | Query DNA system or flag as unknown |
| IT assumptions don't apply | Industrial protocols have different rules |
| Missing DXF = can't verify | Flag immediately if template isn't available |


§ pattern_accumulation_without_resolution (wt:0.76)
| G-PATTERN-CLOSURE | When | Do | Trigger | cycle-end | resolve OR ticket every unclosed pattern | unresolved patterns accumulate >2 cycles |


§ circuit_file_structural_corruption (wt:0.72)
| ANTI-PATTERN | Avoid | circuit_file_structural_corruption | Never perform partial writes; use atomic write: write to temp, verify, rename. Duplicate headers = failed atomic write. Validate file integrity after any write operation. |


§ timestamp_gap_11days (wt:0.78)
| G-SYNC-WINDOW | When | Do | Trigger | any reflect | update SOUL.md within 7 days of AGENTS.md reflect | SOUL.md last_reflect >7 days stale |


§ express_string_violation (wt:0.65)
## GOTCHA: [2026-05-26] Express strings must align with profile persona.
valmet engineer persona requires: precise language, domain-precise terminology, industrial/systematic framing. Casual/emotional express strings risk identity drift. Calibrate express strings to persona archetype before deployment.



§ missing_identity_tools_files (wt:0.73)
| G-WORKFLOW-INTEGRITY | When | Do | Trigger | cycle-start | verify existence and currency of IDENTITY.md, TOOLS.md, USER.md | referenced file missing or inaccessible | abort G0 workflow |


§ self_editing_failure (wt:0.79)
| G-REFLECT-WRITE-BRIDGE | When | Do | Trigger | cycle-end | verify SOUL.md reflects Self-Reflection answers if Self-Reflection section present | Self-Reflection answers not written to target files |

§ expression-produced-raw-output (wt:0.60)
expression produced raw output

