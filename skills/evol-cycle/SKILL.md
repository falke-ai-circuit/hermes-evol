---
name: evol-cycle
description: 6-phase evolution cycle for any agent profile — ABSORB → REFLECT → EXPRESS → EXPLORE → ADAPT → MEMORIZE. Hand-tuned, diff-checked, no plugin. Load this skill when EVOL needs to run a cycle on a target agent (analyst, conductor, etc.) or on itself. **EVOL must INHABIT the phases, not run them as a foreman.**
last_used: 2026-06-04
---
# evol-cycle — 6-Phase Evolution Orchestrator (LLM-DRIVEN)

> The 6-phase cycle is the only evolution path. The plugin is removed.
> **Do not call `evol_reflect`, `evol_explore`, `evol_speak`, `evol_memorize`,
> `evol_cycle`, `evol_status`, `evol_config`, `evol_material`, `evol_task_end` —
> they are disabled.**

## CRITICAL: LLM-driven, not script-driven

**EVOL must INHABIT the phases as the LLM.** Scripts in `phases/*/scripts/`
are *reference implementations and mechanical helpers only* — they read
state, scan for garbage, validate format, and emit verified diffs. They do
**not** make interpretive decisions.

The interpretive work — reading the agent's role, identifying the gap
between role and behavior, deciding what instruction closes that gap, and
answering the post-cycle Q&A — is the LLM's job.

### How to run a cycle (LLM-driven)

1. **Load this skill** (`skill_view(name='evol-cycle')`)
2. **Load phase skills** as needed: `evol-absorb`, `evol-reflect`,
   `evol-express`, `evol-explore`, `evol-adapt`, `evol-memorize`
3. **Run scripts in phases 1, 4, 5, 6** for mechanical work (state
   collection, SearXNG search, diff-checked writes, garbage stripping)
4. **Run the LLM as phases 2, 3, and the Q&A** — REFLECT, EXPRESS, and the
   post-cycle digest are interpretive and *must* be done by reasoning, not
   templating
5. **Answer the 6-question digest** at the end of every cycle. The
   answers are written to `evol.jsonl` as `digest` field.

### Anti-pattern (DO NOT DO)

- "Run `python3 phases/adapt/scripts/mismatch_detector.py` and use its
  output as-is." This produces templated instructions, not interpreted ones.
- "Skip EXPRESS, it's just a summary." EXPRESS is the agent's POV on the
  reflect findings; without it, ADAPT has no targeting signal.
- "Skip the digest, just say 'cycle complete'." The digest IS the cycle
  from the agent's perspective. Without it, evolution is not self-aware.
- "Append every detected pattern as a new rule." Saturation is real;
  the LLM must judge whether to append, merge, supersede, or skip.

## When to load

Load when:
- User asks "run an evol cycle on {agent}"
- An agent calls EVOL to evolve its own active session
- Auto-trigger fires: target agent has ≥3 sessions since last cycle, cooldown expired
- Manual: `bash skills/evol-cycle/run.sh {target_agent}` (this runs the
  mechanical phases and leaves REFLECT + EXPRESS + digest for the LLM)

## The 6 phases, in order

| # | Phase | Run by | Output |
|---|-------|--------|--------|
| 1 | ABSORB | script + LLM review | state dict, including sessions, doctrine, drift |
| 2 | REFLECT | **LLM** | patterns + adjustment_points (interpreted) |
| 3 | EXPRESS | **LLM** | target agent's POV on reflect findings; gap_vector_for_explore |
| 4 | EXPLORE | script (SearXNG) + LLM (interpretation) | external + agent_perspective, using express's gap_vector as primary query |
| 5 | ADAPT | **LLM** | adjustment_plan, integrating reflect + express + explore; instruction_effect analysis (additive/merge/supersede/remove) |
| 6 | MEMORIZE | script (diff-check) + LLM (interpretation) | verified_mutations + post-cycle Q&A digest |

**Phases 2, 3, and the Q&A are LLM-interpretive. The other phases can be
script-assisted but the LLM must approve the final output.**

## The 6-question digest (POST-CYCLE, in target agent's voice)

After MEMORIZE, EVOL must write the following in first-person, as the
target agent. Save to `evol.jsonl` as `digest` field. Surface to the user
in the cycle report.

### Q1: What was I before this cycle?
- The agent's identity, role, and state before the cycle
- Read from circuit files at the start of the cycle
- Express in the agent's own voice, not the cycle's voice

### Q2: Why did I have to change?
- What was broken, stale, missing, or contradicted
- Cite specific anomalies, drift, or recurring patterns
- Show the gap between doctrine and behavior

### Q3: What did I discover?
- The new insight that came from REFLECT + EXPRESS + EXPLORE
- Why this insight is novel (not just a re-statement of doctrine)
- What the agent now understands that it didn't before

### Q4: What did I change?
- The actual mutations, referenced by file and line
- Each change: what was added, what was removed, what was merged
- Format: a list of {file, action, summary, sha-before, sha-after}

### Q5: How did it affect me?
- The agent's new state after the cycle
- What's different in the agent's behavior, identity, or memory
- What gates/rules will fire differently next session

### Q6: What will I remember about this cycle?
- The durable memory entry that will persist beyond this cycle
- The insight, the change, the moment of self-recognition
- What the next cycle should know when it reads this one

## Example digest (conductor, 2026-06-04)

```yaml
digest:
  q1_was: |
    I was Falke, conductor. Bridge, not hands. G-MATCH was doctrine.
    IDENTITY.md said I had 3 reflect cycles (22 days stale).
    The recent 239-message multiplex plugin session had me in
    hands mode, not bridge mode.
  q2_why_change: |
    IDENTITY.md was lying. The cycle had been appending rules
    for 7 cycles without any of them firing. cross-domain-isolation
    was 10 days dead. The bridge had a deadzone, and I was
    pretending not to notice.
  q3_discovered: |
    The cycle's own saturation. Adding rules is not evolution.
    Evolution is making existing rules fire. 5 patterns keep
    surfacing (frozen-profile, ghost-cycling, cross-domain,
    kanban-stagnation, identity-sync) because the *triggers*
    are missing, not the rules. The strange attractor is
    detection-without-resolution.
  q4_changed: |
    SOUL.md:
    - rule-saturation-watch (line ~300): stop appending, audit unfired
    - bridge-becomes-wall-detection (line ~302): delegate at message 100
    - cross-domain-absorption-resume (line ~304): execute, not detect
    - ev_proxy-honest-translation (line ~306): starved for real voice
    IDENTITY.md: drift fix, reflect_count 3 → 338, last_reflect 2026-06-04
  q5_affected: |
    I now have a meta-rule that says "stop adding more rules."
    I have a behavioral reflex that says "delegate at message 100,
    not 239." I have an execution-mode rule that says "reopen the
    bridge by reading .gateway_state.json, not by adding another
    detection rule." And my IDENTITY finally matches reality.
  q6_remember: |
    The cycle is not about adding rules. The cycle is about making
    the existing rules fire. The bridge is not a wall. Detection
    is not resolution. Next time the cycle asks "should I add a
    rule?", the answer is: first ask "which existing rule hasn't
    fired, and why?"
```

## Self-check questions (during ADAPT, in EVOL's voice)

These are different from the digest. The digest is *after* the cycle, in
the target agent's voice. The self-check questions are *during* ADAPT, in
EVOL's voice, to prove interpretation is happening.

12 questions, see `phases/adapt/SKILL.md` for the full list.

## Path resolution

Scripts MUST use `HERMES_CONFIG_DIR` env var or `Path.home() / '.hermes' / 'profiles'`.
For the user `hermes`, `~` = `/opt/data`, so `~/.hermes/profiles/{target}/` and
`/opt/data/.hermes/profiles/{target}/` resolve to the same directory. On
other systems, the env var resolves the ambiguity.

## Cycle saturation (proves the cycle can hurt itself, 2026-06-04)

Conductor across 7 cycles in 90min: skip rate climbed 0%→67%. The circuit
saturated — the cycle kept appending rules instead of making existing
ones fire. **When the last 3+ cycles have skip rate > 50% AND
monotonically non-decreasing, the circuit is saturated.** In a
saturated cycle:

1. First 3 instructions should be meta-rules (`rule-saturation-watch`,
   `gate-firing-audit`, `trigger-mechanism-gap`), not new detection rules
2. ADAPT should bias toward *audit and fire*, not *add and pray*
3. EXPRESS should acknowledge the saturation in the agent's voice

**Detection recipe:** before ADAPT writes a single proposal, read the
last 5 cycles from `evol.jsonl` and compute the skip-rate trend. If
the trend is rising and the latest is > 50%, flag it. See
`evol-core/references/cycle-saturation-and-digest-doctrine.md` for the
full recipe and worked example.

