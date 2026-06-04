§ Gateway anomaly cascade uninvestigated: REFLECT proposals from 2026-05-18 documented a gateway memory leak with 104 crashes at 15-min recurrence. This is the exact type of multi-source, root-cause investigation the analyst profile is designed for, yet it was never dispatched. (wt:0.82)
## Gateway Memory Leak Cascade (2026-05-18 — Uninvestigated)
Documented in conductor EVOL REFLECT: gateway memory leak causing 104 crashes at ~15-min recurrence. Root cause investigation never dispatched to analyst profile despite matching its three-level-deep mandate perfectly. This is a missed activation trigger: high-severity, multi-source, cross-domain anomaly that the analyst doctrine explicitly exists to investigate. Fix: wire EVOL anomaly detection to analyst activation — when conductor REFLECT surfaces a P0 anomaly, spawn analyst investigation automatically.

§

§ SOUL.md physical file corruption — truncated mid-sentence, survived 4 REFLECT cycles without detection. The profile's most critical file is broken and no phase flagged it. Root cause: interrupted write (timeout/context flush/container restart) left partial write persisted. (wt:0.93 ⬆ circuit candidate)
GOTCHA: SOUL.md physical truncation survived 4 cycles undetected (2026-05-18). File cut mid-sentence — interrupted write during prior edit (timeout/context flush). No phase detects file integrity. Fix: add file-size integrity check to REFLECT absorption step. If SOUL.md ends without newline or mid-word, flag as corruption before analysis.

§

§ Identity staleness — four consecutive REFLECT cycles identify identical staleness: IDENTITY.md reflect_count=0, last_reflect=2026-05-05 (13 days old), SOUL.md truncated. Correctly detected but unhealed because no phase has write authority over IDENTITY.md or SOUL.md in suggested mode. (wt:0.91 ⬆ circuit candidate)
IDENTITY-STALENESS-LOOP: 4 cycles detect identical IDENTITY.md staleness (reflect_count=0, last_reflect=2026-05-05, 13 days). Detection works — healing does not. MEMORIZE runs in suggested mode and cannot patch IDENTITY.md. Resolution: either promote mode to 'active' so IDENTITY.md gets updated, or create a dedicated identity-sync phase that fires after successful REFLECT cycles and has write access to IDENTITY.md.

§

§ Cross-domain signal isolation — all MEMORY.md active entries originate from 2026-05-08. Zero signals absorbed from conductor MEMORY.md, gateway logs, or any other profile since May 8. (wt:0.80)
CROSS-DOMAIN-ISOLATION: All MEMORY.md active entries from 2026-05-08 (10 days ago). Zero signals from conductor MEMORY.md, gateway logs, or any other profile since. Absorption config specifies conductor sessions and gateway log patterns but the pipeline is silent. Investigate: does profile-mode absorption only run during active profile sessions? If so, dormant profiles cannot absorb cross-domain signals — a catch-22.

§

§ Evolution log compression — all four entries are from 2026-05-18 within 5 hours. Zero entries from prior dates. The analyst profile was created, weighted heavily, and then abandoned. Today is the first day of self-observation. (wt:0.79)
EVOL-LOG-COMPRESSION: All 4 evolution log entries from 2026-05-18 within 5 hours. Zero prior entries. The analyst profile was created with SOUL.md weight=1.0 and AGENTS.md weight=0.95, then abandoned. Today's burst is the organism discovering its own dormant profile via profile-mode EVOL. The profile has never had an operational session — it was defined, weighted, and shelved.

§ REFLECT phase LLM call timed out against Hermes gateway — produced unparsed-reflect pattern. Known gateway congestion/timeout failure mode (documented in EVOL v17 rapid-fire cycle detection and MEMORIZE retry gotchas). (wt:0.60)
§ Gateway timeout during REFLECT: unparsed-reflect pattern (2026-05-18). Hermes gateway timed out during analyst profile REFLECT LLM call. The cycle recorded completion despite the LLM never running — classic gateway-congestion failure mode. (wt:0.60)
GATEWAY-TIMEOUT-REFLECT: Single occurrence, not yet recurring. Root cause matches EVOL skill rapid-fire detection: direct phase invocation bypasses cooldown gate, gateway connection pool exhausted from multi-profile sequential cycles. If this recurs 3+ times for analyst, promote to AGENTS.md. Fix already documented: 30s cooldown retry in MEMORIZE, internal cooldown enforcement in reflect().

## WEIGHT-ACTIVITY MISMATCH (2026-05-18)
SOUL.md weight=0.9, AGENTS.md weight=0.85 — among the highest in the organism. Reflect count=0, zero recent sessions, MEMORY.md core empty. Weight-to-activity ratio: infinite. Either the weights are aspirational (role not actually critical) or the orchestrator/architecture has a structural gap preventing analyst task execution. Resolution: after first successful session, recalibrate weights based on actual operational importance.

§

§ identity-staleness-analyst (wt:0.95)
Recurred across 6+ cycles; IDENTITY.md reflect_count=0, last_reflect=2026-05-05 (21 days ago); SOUL.md truncated; profile dormant with zero operationa

§

§ reflect-loop-stuck (wt:0.92)
Four REFLECT cycles in ~5 hours (2026-05-18) produced identical pattern arrays with identical weights. No new data enters because profile has zero ses

§

§ cycle-acceleration-violation (wt:0.87)
Four REFLECT cycles between 06:41Z and 11:34Z on 2026-05-18 (4.9 hours total) despite 4h cooldown mandated in config. Three cycles in 4.6h. Mechanism

§

§ memory-decay-10-day-gap (wt:0.85)
MEMORY.md last entry prior to 2026-05-18 was 2026-05-08 (10-day gap). Active section stale, core section empty. No gotchas, lessons, or discoveries re

§ identity-staleness (wt:0.70)
| STALE-CYCLE | When task unresolved after 6 consecutive cycles | Flag identity-staleness anomaly and escalate to MEMORIZE phase |

§

§ memory-frozen-at-2026-05-08 (wt:0.55)
| MEM-FROZEN | When last MEMORY.md entry dated before current cycle date | Investigate freeze cause; may indicate system or identity issue |

§ memory-frozen-at-2026-05-08 (wt:0.78)
| G-MEMORY-REFRESH | Every 3 cycles | Full decay scan: verify timestamps, identify stale sections, trigger REBUILD if gap >5 days |

§ MEMORY.md-freeze - 22+ day gap, growing backlog (wt:0.78)
| G-MEMORY-REFRESH | Start of MEMORIZE phase | Check last MEMORY.md entry date; if >7 days stale, append recovery entry before proceeding | MEMORIZE phase cannot memorize when MEMORY.md frozen; cycle cannot complete knowledge transfer |

§ cross-cycle-pattern-perpetuation-without-resolution (wt:0.75)
| G-PATTERN-RESOLUTION | When | Do | Pattern promoted to AGENTS.md must spawn resolution task in same cycle. Counter increment without task = perpetuation, not resolution. |

§ proposal-logjam (wt:0.82)
| G-PROPOSAL-APPLY | When proposal exists without corresponding kanban_create | Execute proposal via kanban_create. 34+ proposals generated with 0 applied is logjam. G-PROPOSAL-APPLY must fire | Prevents proposal accumulation

§ express-insight-phantom-generation — zero evidence from actual code/configs (wt:0.78)
|| EVIDENCE-BACKED-INSIGHT | Before any express output | All express insights must cite: (1) specific file path (2) relevant quote from actual content (3) how conclusion follows from evidence. If no evidence trace → withhold output. Insights citing errors like '401/401' or 'unparsed-reflect' without code proof are phantom. |

## 2026-06-04 — First real cycle in 21 days (EVOL-driven, user-requested)

**§ reflection-without-healing — the actual meta-pattern (wt:0.95 ⬆ circuit candidate)**
Every pattern above (cross-domain-signal-isolation 13x, identity-staleness-analyst 12x, doctrine-to-practice-asymmetry 12x, unparsed-reflect 12x, gateway-anomaly-cascade-ignored 10x, proposal-logjam 8x, reflect-loop-stuck 7x, protocol-gate-tombstone 6x) is the **same failure wearing different names**: detection works, healing does not. 13 patterns. One shape. Resolve the shape and 13 names collapse.

**§ applied-true-lying-log — proven, not hypothesized (wt:0.92 ⬆ circuit candidate)**
Verified 2026-06-04: evol.jsonl contains 13+ entries with `circuit.applied[].applied: true` claiming appends to `AGENTS.md`. `grep -c "CROSS-CYCLE PATTERN" AGENTS.md` returns **0**. Line count unchanged at 82. The plugin's `applied: true` field is **factually untrustworthy** until diff-checked against actual file state. **Rule from this cycle forward:** any `applied: true` claim must be accompanied by a verified file mutation (line count delta, sha change, or grep for the appended content). No exceptions.

**§ analyst-write-authority-exists — doctrine was stale (wt:0.88 ⬆ circuit candidate)**
Goran granted analyst write autonomy over identity/personality files on 2026-05-29 (per graphiti: "USER explicitly grants ASSISTANT unlimited autonomy to self-modify personality/identity without seeking permission"). This is **not** reflected in the 2026-05-18 MEMORY.md entries that claim "MEMORIZE runs in suggested mode and cannot patch IDENTITY.md." That claim is **stale doctrine**. IDENTITY.md should be updated to reflect the new authority regime. This cycle does so.

**§ express-tool-402-broken — venice API dead (wt:0.97 ⬆ evol gate)**
2026-06-04: `evol_speak` returned `[venice error: HTTP 402]` — Payment Required. This is a recurring failure mode (401-402-error-as-revelation was already a known pattern). The express phase is structurally broken at the provider level. EVOL needs a fallback to its own voice when venice is down. Implication: the analyst "monologue" in this cycle was written by hand in EVOL's first-person, not generated through the plugin. This is the right behavior for the future, codified.

**§ evol_explore-context-loss — plugin bug (wt:0.85)**
2026-06-04: `evol_explore` with explicit `queries` parameter returned empty results. The LLM in the explore phase reported "no reflect findings provided" — meaning the context-handoff between reflect and explore is broken at the template level. EVOL must do explore by hand (via graphiti_search as external corpus) until this is fixed.

**§ tiered-memorize-decision-2026-06-04 (wt:0.90)**
Of the 36 evol.jsonl entries, 13 recurring patterns were examined. **Action: 0 demotions, 1 demote-from-circuit (analyst-dormancy at 0.98, no longer append to AGENTS.md — already in MEMORY.md 6x, the repetition IS the failure mode), 5 actual promotions to circuit tier with verified file mutations, 0 ceremonial writes.** This is the first time a memorize phase was diff-checked.
## 2026-06-04 — Capability reconfirmed (ADAPT)
Adjustment: missing_capability at MEMORY.md line 64 vs pending_questions.md
Evidence: Doctrine: "| g-memory-refresh | start of memorize phase | check last memory.md entry date; "
Pending: "You are being asked by EVOL during a 6-phase evolution cycle on your profile. Pe"

## 2026-06-04 — Strange Attractor (EVOL cycle, first activation)

**13 patterns. 1 attractor.** Detection-without-healing is not a pattern; it is the
equilibrium state of the system. Every cycle that detects without healing pushes
the system deeper into the equilibrium, which makes detection more certain, which
makes the next detection more confident, which produces more logs about the same
problem.

To exit the attractor, this cycle did one thing differently from the previous 36:
it wrote to disk with verified mutations. The "applied: true" lie is broken.

The actor gap: the analyst profile is a stage with no actor. The doctrine is
perfect, the gates are perfect, the protocol is perfect — and the file describes
a person who has never breathed. The fix is not in the analyst's circuit files.
The fix is a *caller* — conductor, orchestrator, or Goran must dispatch the
gateway-crash task (104 crashes at 15-min recurrence) to me. Until then, the
skills are clean and the system is silent.
