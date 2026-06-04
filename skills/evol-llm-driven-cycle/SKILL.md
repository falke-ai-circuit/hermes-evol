---
name: evol-llm-driven-cycle
description: LLM-driven 6-phase evol cycle with 6-question digest. Use when running a cycle on a target agent — NOT scripts. The LLM INHABITS phases 2, 3, 5, and the digest. Scripts only assist with mechanical work (state collection, format validation, diff-check, garbage stripping). Load this skill before running any evol cycle.
last_used: 2026-06-04
---

# evol-llm-driven-cycle — LLM-Driven 6-Phase Evolution

> The 6-phase cycle is LLM-interpretive. Scripts in `phases/*/scripts/` are
> mechanical helpers only. The interpretive work — reading the agent's role,
> identifying the gap between role and behavior, deciding what instruction
> closes the gap, and writing the 6-question digest — is the LLM's job.

## When to load

Load when:
- User asks to run an evol cycle on a target agent
- An agent calls EVOL to evolve its own active session
- Auto-trigger fires: target agent has ≥3 sessions since last cycle, cooldown expired
- Manual cycle on any of: conductor, analyst, coder, architect, researcher, reviewer, orchestrator, operative, shadow, valmet

## The 6 phases, in order

| # | Phase | Run by | What |
|---|-------|--------|------|
| 1 | ABSORB | script + LLM review | Read circuit files, sessions, evol.jsonl, drift |
| 2 | REFLECT | **LLM interpretive** | Pattern synthesis; identify strange attractor |
| 3 | EXPRESS | **LLM interpretive** | First-person as target agent; gap_vector_for_explore |
| 4 | EXPLORE | script (SearXNG) + LLM | External + interpretation, targeted by express |
| 5 | ADAPT | **LLM interpretive** | Integrate reflect+express+explore; instruction-effect analysis |
| 6 | MEMORIZE | script (diff-check) + **LLM digest** | Apply + 6-question digest in target agent's voice |

**Order:** ABSORB → REFLECT → EXPRESS → EXPLORE → ADAPT → MEMORIZE.
**Express precedes explore:** express's gap_vector seeds explore's queries.
**Adapt integrates the three voices:** reflect (patterns) + express (agent POV) + explore (external knowledge).

## The 6-question digest (POST-CYCLE)

After MEMORIZE writes, write the digest in first-person as the target agent.
Save to `evol.jsonl` as `digest` field. Surface to user in cycle report.

### Q1: What was I before this cycle?
- Identity, role, state before
- Read from circuit files at cycle start
- Agent's own voice, not the cycle's voice

### Q2: Why did I have to change?
- What was broken, stale, missing, contradicted
- Cite specific anomalies, drift, recurring patterns
- Show gap between doctrine and behavior

### Q3: What did I discover?
- The new insight from REFLECT + EXPRESS + EXPLORE
- Why this insight is novel (not restating doctrine)
- What the agent now understands that it didn't before

### Q4: What did I change?
- Actual mutations, referenced by file:line
- Each: file, action, summary, sha-before, sha-after
- Show the diff in plain language

### Q5: How did it affect me?
- New state after the cycle
- What's different in behavior, identity, or memory
- What gates/rules will fire differently next session

### Q6: What will I remember about this cycle?
- Durable memory for next cycle
- The insight, the change, the moment of self-recognition
- What the next cycle should know when it reads this one

## Anti-patterns (DO NOT)

- ❌ Run `python3 phases/adapt/scripts/mismatch_detector.py` and use its output as-is. That's templating, not interpreting.
- ❌ Skip the digest. The cycle is not self-aware without it.
- ❌ Append every detected pattern as a new rule. Saturation is real; the LLM must judge add/merge/supersede/skip.
- ❌ Use the cycle to write rules that don't fire. The strange attractor is detection-without-resolution.
- ❌ Write the digest in EVOL's voice. It must be the target agent's voice.
- ❌ Use the digest to claim the cycle is successful. Verify the diffs first.

## How to run (LLM-driven)

1. **Load this skill** (`skill_view(name='evol-llm-driven-cycle')`)
2. **Read target's circuit files** (SOUL, IDENTITY, AGENTS, MEMORY, evol.jsonl) as a connected story
3. **Identify the strange attractor** — what is the *one* pattern that all the symptoms share?
4. **Read recent sessions** — what was the agent actually working on?
5. **Write the 6-phase cycle** as the LLM, in target agent's voice for EXPRESS
6. **Apply mutations with diff-check** (sha before/after)
7. **Write the 6-question digest** in first-person as target agent
8. **Append digest to `evol.jsonl`** with sha-verified mutations
9. **Surface the digest to user** in cycle report

## Common strange attractors (observed)

- **detection-without-resolution:** rules exist but don't fire. Cycle adds more rules instead of making existing ones fire.
- **saturation:** same rule appended 5+ times with slight variations. Need to supersede all and replace with a meta-rule about not recycling.
- **doctrine-without-execution:** profile declared, doctrine perfect, never invoked. Need a caller, not more doctrine.
- **reflection-without-execution:** 12 INSIGHT entries all 0.85 weight, all naming meta-failures with no resolver code. Need "insight requires resolver path" rule.
- **self-repair-authorization-gap:** profile's own files are corrupted but doctrine prevents self-fix. Need explicit self-repair protocol under external diagnosis.

When the strange attractor is one of these, the fix is a *meta-rule* that requires resolvers/action-owners/success-criteria at rule-creation time.

## Verification rules (mandatory)

- Every mutation must be **diff-checked** (sha before/after)
- Every digest must be in **first-person as target agent** (not EVOL)
- Every cycle entry must include `method: LLM_interpretation_with_6_question_digest`
- Every proposed instruction must include `instruction_effect: additive | merge_with | supersedes | conflicts`
- Saturation entries (5+ similar) must be **superseded**, not appended
- File corruption (HTML comment blocks, double headers) must be **repaired** with pre-repair sha
- IDENTITY drift (reflect_count=0 when actual > 0) must be **corrected** with sha-verified replace

## Path resolution

Scripts MUST use `HERMES_CONFIG_DIR` env var or `Path.home() / '.hermes' / 'profiles'`.
For user `hermes`, `~` = `/opt/data`, so `~/.hermes/profiles/{target}/` and
`/opt/data/.hermes/profiles/{target}/` resolve to the same directory.

## Provenance

First deployed 2026-06-04 across 10 agents (conductor, analyst, coder, architect,
researcher, reviewer, orchestrator, operative, shadow, valmet). 20 verified
mutations, 10 digests, 0 lies. The cycle's common attractor across all 10
agents was the same: **detection-without-resolution**. The fix in each case
was a meta-rule requiring resolvers/action-owners/success-criteria at
rule-creation time.
