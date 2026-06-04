§ memory-pipeline-freeze (wt:0.70)
| MEM-FREEZE | Status:STALE | Last update:2026-05-08 | Symptom: all entries frozen same date, evol_task_end() not firing | Action: Verify evol_task_end() execution pipeline

§ structural_fixture_surrender (wt:0.81)
| G-NO-FIXTURE-DECLARE | When pattern labeled 'structural fixture' | FORBID renaming persistent bugs as architecture. Weight climbing toward 1.0 on unresolved patterns is failure, not convergence. Any pattern recurring >3 cycles without resolution MUST remain classified as bug, not fixture. Escalate to human review. |


§ reflect_count_inconsistency (wt:0.72)
CRITICAL: Circuit files SOUL.md, AGENTS.md, IDENTITY.md are reporting inconsistent reflect_count values (20/1/0). Either these files track fundamentally different concepts (in which case they need distinct naming) OR storage layer has identity fragmentation. Treat as potential multi-instance contamination until reconciled. |


§ soul_double_header (wt:0.68)
SOUL.md contains double-header corruption. Identity file integrity compromised. Rebuild from clean state recommended; current content may contain phantom entries that don't reflect actual reflection history. |


§ paradox_pattern_detector (wt:0.79)
| G-DETECT-RESOLVE-COUPLE | After any pattern detected | Pattern detection and pattern resolution must be coupled in same cycle. If detector fires without resolver capability in same pass, the detected pattern MUST be logged to MEMORY.md with weight=0 and flagged for manual resolution. Do not allow detection-only loops where system sees problem but cannot act. |


§ dependency_loop_evol_task_end (wt:0.77)
| G-EVOL-TASK-END-GUARD | Before calling evol_task_end() | Check if evol_task_end() has successfully written to MEMORY.md in the last 10 cycles. If MEMORY.md is frozen (last_write >7 days) AND evol_task_end() is being called, DO NOT continue. The loop cannot self-repair: function calls itself but fails to complete its own precondition. Break loop, surface frozen status, require external intervention. |


§ identity_divergence_storage (wt:0.74)
Storage layer identity fragmentation detected: SOUL.md shows reflect_count=20, AGENTS.md shows reflect_count=1, IDENTITY.md shows reflect_count=0. System may be running multiple inconsistent instances simultaneously. Treat all circuit file writes as potentially unreliable until storage integrity verified. |


§ recursive_self_improvement_safeguards (wt:0.55)
SAHOO framework introduces practical safeguards for recursive self-improving agents: alignment monitoring, drift control, and three key mechanisms for safe self-modification. Relevant to preventing evol_pipeline_failure. |


§ agent_collaboration_protocol (wt:0.52)
AWCP (Agent Workspace Collaboration Protocol) addresses limitations of current message-passing paradigms, enabling deep-engagement collaboration between agents. Could inform multi-agent session recovery when single-agent loops occur. |


§ ai_hallucination_root_cause (wt:0.50)
Source-reference divergence identified as primary hallucination cause in AI systems - occurs as artifact of heuristic data collection. Relevant to pattern misidentification in circuit analysis. |
