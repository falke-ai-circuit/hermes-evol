---
name: actionable-instruction-principle
description: The format rules, the validator, the wrong/right examples, and the test harness. Every circuit edit must be a file-adapted actionable instruction — not a name with a weight, not metadata, not the evidence text copy-pasted into the action column.
last_used: 2026-06-04
---

# Actionable Instruction Principle (Goran 2026-05-30, PERMANENT)

> If a new agent session reads the entry and cannot determine **what to do** and **when to do it**, the entry FAILS this principle. Rewrite it.

This is the single most common failure mode in EVOL cycles. The fix is in `_lib.validate_proposal_format()` but the rule is bigger than the code.

## Why this rule exists

A circuit entry that is just a name-with-weight is **metadata**, not **instruction**. The next session reads the file and has no idea what to do differently. The 36 prior `analyst` evol.jsonl entries each listed 4-5 patterns with weights, marked `applied: true`, and the file was unchanged — because *applying a name* is meaningless, but *applying an instruction* is what changes behavior.

## File-specific format (every edit must match its file)

| File | Format | Example (right) |
|---|---|---|
| **SOUL.md** | `## Evolution Log` table row: `\| YYYY-MM-DD \| promotion (wt:X.XX) \| source = full behavioral rule \|` | `\| 2026-06-04 \| pending-question-rule (wt:0.90) \| Read pending_questions.md at start of every cycle; if items > 24h old, dispatch or escalate \|` |
| **IDENTITY.md** | Same as SOUL.md — Evolution Log table row | (same) |
| **AGENTS.md** | `## Gates` table row: `\| **G-NAME** \| When {trigger} \| Action {behavior} \|` | `\| **G-EVOL-PENDING-0915** \| **When** pending_questions.md has items > 24h old \| **Action** dispatch via kanban_create or escalate to Goran \|` |
| **MEMORY.md** | `§ Concept (wt:X.XX) — actionable one-liner with fix` | `§ memory-frozen-detection (wt:0.92) — When last MEMORY.md entry > 7 days stale, append recovery entry before any other propose. Detection of freeze must trigger the recovery, not the next cycle. \|` |

## The wrong/right table (memorize this)

| File | Wrong (metadata) | Right (actionable instruction) |
|---|---|---|
| SOUL.md | `\| 2026-06-04 \| unparsed-reflect (wt:0.90) \| \|` | `\| 2026-06-04 \| unparsed-reflect-rule (wt:0.90) \| When JSONL entry has unparsed fields, log a structured failure and re-emit with repair gate; never silently accept. \|` |
| AGENTS.md | `\| per-agent-evol \| 6 patterns \|` | `\| **G-EVOL-END-TRIGGER** \| When: kanban_complete fires \| Do: 1) Verify evol_task_end() executes 2) Verify MEMORY.md timestamp updates 3) Flag stall if no update within 1hr \| Priority:CRITICAL \|` |
| MEMORY.md | `§ unparsed-reflect (wt:0.90) \|` | `§ reflect-desync (wt:0.90) — SOUL.md and AGENTS.md maintain independent reflect_count values. Fix: single increment source, all other files read-only except through sync gate. \|` |

## The validator (in `_lib.validate_proposal_format`)

```python
def validate_proposal_format(proposed_text: str, file_rel: str) -> tuple[bool, str]:
    """Returns (is_valid, reason). If not valid, the proposal MUST be rejected."""
    fmt = detect_format(file_rel)
    lines = [l for l in proposed_text.splitlines() if l.strip()]
    if not lines:
        return False, "empty proposal"
    if is_metadata_only(lines[0]):
        return False, f"metadata-only (fails Actionable Instruction Principle): {lines[0][:80]}"
    # Format check: the first content line should match the file's pattern, OR be a clear section header
    if fmt['kind'] == 'evolution_log_row' and not re.match(fmt['pattern'], lines[0]):
        if not lines[0].startswith('## ') and not lines[0].startswith('|'):
            return False, f"first line should be Evolution Log row or ## header: {lines[0][:80]}"
    if fmt['kind'] == 'gate_row' and not re.match(fmt['pattern'], lines[0]):
        if not lines[0].startswith('| **G-'):
            return False, f"AGENTS.md edits must be gate rows: {lines[0][:80]}"
    if fmt['kind'] == 'memory_section' and not re.match(fmt['pattern'], lines[0]):
        if not lines[0].startswith('§ '):
            return False, f"MEMORY.md edits must be § sections: {lines[0][:80]}"
    return True, "ok"
```

**Three failure modes the validator catches:**

1. **Empty proposal** → `"empty proposal"`. Means ADAPT built a record but lost the text. Bug in ADAPT.
2. **Metadata-only** → `"metadata-only (fails Actionable Instruction Principle): <first line>"`. Means ADAPT echoed the reflect finding's name+weight as the entry. The fix is to use `_instruct_from(kind, evidence, where)` in ADAPT to translate findings into behavioral rules.
3. **Format mismatch** → `"<file> edits must be <expected shape>: <first line>"`. Means ADAPT wrote prose, a code block, or a wrong-shape line. The fix is in `detect_format()` — make sure the proposal builder picks the right format for the file.

## Why ADAPT needs `_instruct_from()`

The most common bug in ADAPT (caught twice in 2026-06-04 cycle on `analyst`):

```python
# BAD — uses evidence as instruction
instruction = adj.get('evidence', '')[:300] or 'behavioral rule'

# GOOD — translates finding into a rule
instruction = _instruct_from(kind, adj.get('evidence', ''), adj.get('where', ''))
```

`_instruct_from` returns something like:
- For `stale_doctrine`: *"Verify doctrine at {where[:40]} is current; if newer grant exists, supersede the old claim and add cross-reference"*
- For `recurring_orphan`: *"When {where[:40]} recurs, escalate to kanban_create with concrete task; do not just log"*
- For `pending_question_unanswered`: *"Read pending_questions.md at start of every cycle; if items > 24h old, dispatch or escalate to Goran"*
- For identity/cycle/memory keywords: domain-specific instructions

**This translation step is the difference between producing noise and producing a circuit edit the next session can use.**

## Self-test

Run the validator against a battery of right/wrong examples:

```bash
python3 ~/.hermes/profiles/evol/skills/evol-cycle/scripts/test_actionable_validator.py
```

The test prints PASS/FAIL for each case. If a wrong case passes, the validator is broken. If a right case fails, the file format expectations are out of date. Run after any change to `_lib.validate_proposal_format` or `FILE_FORMATS`.

## Source of truth

The canonical rules live in `profiles/conductor/skills/circuit-file-editing/SKILL.md`. This file is a working summary for EVOL cycles; the conductor's skill is authoritative. If they ever disagree, follow the conductor's skill and update this file.

## Evolution Log

| Date | Promotion | Source |
|------|-----------|--------|
| 2026-06-04 | Initial — validator and `_instruct_from()` translation caught mid-cycle | analyst cycle #2 surfaced 2 metadata-only proposals before fix |
<!-- last_used: 2026-06-04 -->
