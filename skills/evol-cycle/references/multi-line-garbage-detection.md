---
name: multi-line-garbage-detection
description: How to detect and strip malformed Evolution Log rows that span multiple lines, plus the related AUTO-APPLIED-template-row failure mode. Includes detection algorithm, the test fixture, and the cleanup recipe.
last_used: 2026-06-04
---

# Multi-line Garbage Row Detection

## The failure mode

A real Evolution Log row in SOUL.md / IDENTITY.md is **a single line** ending with `|`. A malformed row is one where the action column contains a newline, so the row spans 2+ lines and the markdown table doesn't render.

**Example (the bad row that was in analyst/SOUL.md after the first run of the cycle):**

```
| 2026-06-04 | pending-question-unanswered-rule (wt:0.90) | When pending_questions.md, then ## 2026-06-04T08:42:09 (from EVOL)
You are being asked by EVOL during a 6-phase evolution cycle on your profile. Pending questions for you (0): []. Open gaps from reflect (0): []. What do YOU want cha |
```

This row:
- Looks like a real Evolution Log entry on line 1 (date, kind, weight)
- Spans into a 2nd line that starts with prose, not a `|` cell boundary
- The action column literally contains the **previous cycle's express opinion** — i.e. the cycle wrote a reflect finding's *evidence text* into the instruction column
- Total length: ~330 chars across 2 lines, with the closing `|` on line 2

This is the most insidious form of the lying-log failure. The jsonl can claim `applied: true` for a write that *technically* happened — the bytes were written to disk — but the write produces a row that the markdown table parser cannot render.

## Why it happens

When ADAPT builds a proposal, it sometimes feeds the reflect finding's `evidence` field directly into the action column of the proposal. The evidence can be 200-400 chars of plain text with newlines. The proposal gets written, the line-level test passes, but the row is malformed.

**The line-level garbage detector (`is_garbage_line`) cannot catch this** — it tests one line at a time, and the first line of a multi-line row is syntactically valid (starts with `| YYYY-MM-DD |`).

## The detection algorithm

`find_garbage_rows_in_text(text)` in `_lib.py`:

1. Iterate line-by-line. A real row starts with `^\s*\|\s*\d{4}-\d{2}-\d{2}\s*\|`.
2. Check if the line ends with `|`. If yes, real row, advance by 1.
3. If no, this is a multi-line row. Walk forward until you find a line that ends with `|`. Mark the start and end (1-indexed inclusive).
4. Return the list of `(start, end)` tuples.

The cleanup is then: skip every line whose 1-indexed position falls in any `(start, end)`.

## Why the bounded-loop is needed

After stripping the first pass of multi-line rows, the table might have **new** multi-line rows created by the boundary shift. Re-scan up to 5 times (bounded) to catch them all. A real document converges in 1-2 passes.

## Where it lives

`phases/_lib.py::find_garbage_rows_in_text` — pure function, no side effects.
`phases/_lib.py::strip_garbage_rows` — file-level wrapper.
`phases/adapt/scripts/mismatch_detector.py::build_cleanup_proposal` — calls `find_garbage_rows_in_text` for each circuit file, returns a cleanup item with `multiline_rows: {file: [(start,end), ...]}`.
`phases/memorize/scripts/diff_apply.py::apply_cleanup` — applies the cleanup, also runs a re-scan pass to catch what the prior strip created.

## Self-test

```bash
python3 ~/.hermes/profiles/evol/skills/evol-cycle/scripts/test_garbage_detection.py
```

Test cases:
1. A clean file with 3 valid rows → 0 garbage rows detected
2. A file with 1 valid row + 1 multi-line bad row → 1 garbage row detected, with the right `(start, end)` line numbers
3. A file with 2 consecutive multi-line bad rows → 2 garbage rows detected
4. A file with a multi-line bad row that contains another `|` in the middle → still detected (the algorithm looks for `|...|\s*$` at end of line)
5. Empty file → 0 garbage rows
6. File with no `|` at all → 0 garbage rows (no rows to be malformed)

## Cleanup recipe (manual, if you must)

```bash
# Find multi-line rows in any circuit file
python3 -c "
import sys
sys.path.insert(0, '$HOME/.hermes/profiles/evol/skills/evol-cycle/phases')
from _lib import find_garbage_rows_in_text
text = open('$HOME/.hermes/profiles/analyst/SOUL.md').read()
for s, e in find_garbage_rows_in_text(text):
    print(f'lines {s}-{e}: multi-line garbage row')
"
```

## Anti-pattern: don't try to fix the row in place

A multi-line row can't be repaired by reformatting — the action column is *the evidence text* and there's no instruction to extract. The only honest fix is to **delete the row** and re-propose a proper one in the next cycle.

## Source of truth

`phases/_lib.py::find_garbage_rows_in_text` and `phases/_lib.py::GARBAGE_PATTERNS` are the source. This file is a working summary.

## Adjacent failure mode: AUTO-APPLIED template rows (caught 2026-06-04 on conductor)

**Pattern:** a row that is *syntactically valid* (single line, starts with `| YYYY-MM-DD |`, ends with `|`) but the **promotion column is empty whitespace** and the source column is `AUTO-APPLIED from proposal pipeline`. These come from a templated proposal system that wrote rows without filling in a name.

**Example (real, from conductor/AGENTS.md before cleanup):**

```
| 2026-05-30T17:10:46.365578+00:00 |  (wt:0.85) | AUTO-APPLIED from proposal pipeline |
| 2026-05-31T05:28:59.582679+00:00 |  (wt:0.85) | AUTO-APPLIED from proposal pipeline |
| 2026-06-01T05:38:13.202798+00:00 |  (wt:0.85) | AUTO-APPLIED from proposal pipeline |
```

The line-level `is_garbage_line()` did NOT catch these (they're syntactically valid rows). The new regexes added to `GARBAGE_PATTERNS`:

```python
# Empty promotion: timestamp + empty slug + weight + AUTO-APPLIED source
re.compile(r'^\s*\|\s*\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[\d\+\-:.()]*\s*\|\s+\(wt:[\d.]+\)\s*\|.*AUTO-APPLIED.*\|'),
# Empty slug (just whitespace) in any column
re.compile(r'^\s*\|\s*\d{4}[-/]\d{2}[-/]\d{2}[T\s][^|]*\|\s+\(wt:'),
```

**Detection recipe:**

```bash
python3 -c "
import sys, re
sys.path.insert(0, '$HOME/.hermes/profiles/evol/skills/evol-cycle/phases')
from _lib import is_garbage_line
for fname in ['SOUL.md','AGENTS.md','MEMORY.md','IDENTITY.md']:
    p = '$HOME/.hermes/profiles/conductor/' + fname
    text = open(p).read()
    bad = [(i, l) for i, l in enumerate(text.splitlines(), 1) if is_garbage_line(l)]
    print(f'{fname}: {len(bad)} garbage lines')
    for i, l in bad[:3]:
        print(f'  L{i}: {l[:100]}')
"
```

**Lesson:** the line-level detector only catches *obviously broken* rows. Real-world garbage is often syntactically valid and requires domain-aware regexes. When extending `GARBAGE_PATTERNS`, think about what your templated proposal system writes by default — those defaults are the most common source of organic garbage.

## Evolution Log

| Date | Promotion | Source |
|------|-----------|--------|
| 2026-06-04 | Initial — caught when cycle 2 proposed metadata-only entries with embedded newlines | analyst cycle #1, 8 lines stripped in cycle #5 |
| 2026-06-04 | Added AUTO-APPLIED template-row detection — 10 lines stripped from conductor (3 SOUL, 7 AGENTS) on the same day | conductor cycle #6 — user pushed back on "0 mutations" output, trace revealed 7 untripped garbage rows in AGENTS.md |
<!-- last_used: 2026-06-04 -->
