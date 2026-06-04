---
name: memorize-tier-transitions
description: The tier-aware write doctrine for MEMORIZE. Why every write must be diff-checked, format-validated, and explicitly tier-aware. Multi-line garbage detection. The promote/demote/cleanup contract.
last_used: 2026-06-04
---

# MEMORIZE — Tier-Aware Diff-Checked Writes

> **Goran 2026-06-04:** *"memorize must understand how to promte and move memories through different tiers etc"*

## Why tier transitions matter

The old plugin's MEMORIZE wrote blindly with `applied: true` and no tier awareness. 36 cycles produced 0 actual file mutations and 18 cross-cycle "stale" patterns. The new MEMORIZE has 4 explicit tier transitions:

| Action | Tier | What it means |
|---|---|---|
| `append` to SOUL/AGENTS/IDENTITY | `CIRCUIT` (weight ≥ 0.85) | Promote to durable doctrine. Real instruction, not metadata. |
| `append` to MEMORY.md | `MEMORY` (weight ≥ 0.65) | Working memory. Same format rules. |
| `append_demotion_marker` to MEMORY.md | `KNOWLEDGE` (weight < 0.35) | Demote from circuit. Tag with `demoted-{name}`. |
| `replace` on IDENTITY.md | `CIRCUIT` | Drift correction. Only when `temporal_doctrine.drift > 0`. |
| `cleanup` on circuit files | `KNOWLEDGE` | Strip CROSS-CYCLE PATTERN spam + multi-line garbage rows. |

## The hard rules

### 1. Diff-check every write in the same cycle

```python
def apply_append(profile, file_rel, text):
    path = profile / file_rel
    if not path.exists():
        return {"verified": False, "reason": f"file_not_found:{file_rel}"}
    before = path.read_text(errors='replace')
    sha_before = sha256(before)
    if text.strip() in before:
        return {"verified": False, "reason": "duplicate"}
    ok, reason = validate_proposal_format(text, file_rel)
    if not ok:
        return {"verified": False, "reason": f"format_invalid: {reason}"}
    after = before + text
    path.write_text(after)
    sha_after = sha256(after)
    return {"verified": True, "file": file_rel, "delta_lines": after.count('\n') - before.count('\n'),
            "sha_before": sha_before, "sha_after": sha_after}
```

The output contract: `verified_mutations: [{file, delta_lines, sha_before, sha_after, tier, instruction_format}]`. **`applied: true` without a verified mutation is the lying-log failure mode. Forbidden.**

### 2. Reject metadata-only proposals

A `name (wt:0.XX)` with no actionable content fails the Actionable Instruction Principle. The validator catches this:

```python
def is_metadata_only(text):
    stripped = text.strip()
    return any(p.match(stripped) for p in [
        re.compile(r'^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*[\w-]+\s*\(wt:\d+\.\d{2}\)\s*\|\s*\|?\s*$'),
        re.compile(r'^\|\s*\*\*G-[\w-]+\*\*\s*\|\s*When.*Do\s*\|\s*[\w-]+\s*\|\s*$'),
        re.compile(r'^§\s+[\w-]+\s*\(wt:\d+\.\d{2}\)\s*—\s*\.?\s*$'),
    ])
```

If a proposal is metadata-only, MEMORIZE rejects it with `reason: format_invalid: metadata-only (fails Actionable Instruction Principle)`. The proposal goes to `skipped`, not `verified_mutations`.

### 3. Validate the file-format match

Each file has a required format (see `references/actionable-instruction-principle.md`):

| File | Format | Validator pattern |
|---|---|---|
| SOUL.md | Evolution Log row | `^\|\s*\d{4}-\d{2}-\d{2}\s*\|[^|]+\(wt:\d+\.\d{2}\)\s*\|[^|]+\s*\|$` |
| AGENTS.md | Gate row | `^\|\s*\*\*G-[A-Z0-9_-]+\*\*\s*\|` |
| IDENTITY.md | Evolution Log row | same as SOUL.md |
| MEMORY.md | § section | `^§\s+\S.+\(wt:\d+\.\d{2}\)\s*—\s*\S+` |

The validator's first non-empty line must match the file's pattern. MEMORIZE rejects with `format_invalid: first line should be Evolution Log row or ## header: ...` if it doesn't.

### 4. Path resolution via env var

`/opt/data/profiles/` is hardcoded — bad. The `_lib.profiles_root()` chain is:
- `HERMES_CONFIG_DIR` if set
- `HERMES_DATA` + `/profiles` if set
- `~/.hermes/profiles` if it exists
- `~/config_root/profiles` fallback

```python
def profiles_root() -> Path:
    explicit = os.environ.get('HERMES_CONFIG_DIR')
    if explicit:
        return Path(explicit) / 'profiles'
    data = os.environ.get('HERMES_DATA')
    if data:
        return Path(data) / 'profiles'
    home_hermes = Path.home() / '.hermes' / 'profiles'
    if home_hermes.exists():
        return home_hermes
    return Path.home() / 'config_root' / 'profiles'
```

The default must check existence, not just return. The bug was: on the `hermes` user, `~` = `/opt/data`, and `~/config_root/profiles` doesn't exist. The fix checks for `~/.hermes/profiles` first.

### 5. JSONL audit entry per cycle

```python
jsonl_entry = {
    "profile": "evol",
    "mode": "manual",
    "target_agent": target,
    "cycle_id": f"evol-on-{target}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
    "timestamp": datetime.now().isoformat(timespec='seconds'),
    "phases_executed": ["absorb", "reflect", "express", "explore", "adapt", "memorize"],
    "express": {"voice": "...", "gap_vector_size": N},
    "memorize": {"items_scored": N, "verified_mutations": M, "skipped": K, "demotions": D},
}
with evol_jsonl.open('a') as f:
    f.write(json.dumps(jsonl_entry) + '\n')
```

The new `evol.jsonl` starts fresh (the old log is quarantined as `evol.jsonl.historical-2026-06-04`). Historical entries can be imported with `untrusted: true` if needed for analysis, but the new log only records verified mutations.

## Multi-line garbage detection (the catch-22)

**Bug (caught 2026-06-04):** Earlier cycles wrote Evolution Log rows with multi-line action columns (the action text contained a newline, so the row spanned 2 lines). My line-level garbage detector missed them. The cycle's cleanup reported `0 garbage lines` while the file was full of malformed rows.

**Fix:** A real Evolution Log row is a single line that ends with `|`. A row that spans multiple lines is malformed. The detector walks line-by-line, finds rows that don't terminate with `|` on the same line, and marks the whole multi-line span as garbage:

```python
def find_garbage_rows_in_text(text):
    lines = text.splitlines()
    garbage_rows = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not re.match(r'^\s*\|\s*\d{4}-\d{2}-\d{2}\s*\|', line):
            i += 1
            continue
        if line.rstrip().endswith('|'):
            i += 1
            continue
        # Multi-line row detected
        start = i
        while i < len(lines) and not lines[i].rstrip().endswith('|'):
            i += 1
        end = i  # inclusive (terminator line)
        garbage_rows.append((start + 1, end + 1))  # 1-indexed
        i += 1
    return garbage_rows
```

The cleanup applies this in 3 steps: (1) line-level garbage (CROSS-CYCLE PATTERN spam), (2) multi-line garbage rows, (3) re-scan loop to catch any rows the prior step created.

## Bug history

- **2026-06-04 (caught in 1st run):** `apply_append` was hardcoded to write to stdout only, ignoring `-o/--output` flag. Bash `run.sh` chained phases via `> /tmp/...json` redirection, but the script's `json.dump(state, sys.stdout, ...)` overwrote the redirect. Phase 2 then failed with `cannot read absorb state: {}`. Fix: argparse with `-o/--output`, `Path(args.output).write_text()` if set.
- **2026-06-04 (caught in 2nd run):** `apply_append` body was replaced with `apply_replace` body by an over-aggressive patch. The script then silently dropped the append action. Fix: rewrite the whole file with clean function definitions.
- **2026-06-04 (caught in 3rd run):** `apply_replace` was never added to the action dispatch. ADAPT proposed `replace` actions (for IDENTITY.md drift correction), but MEMORIZE didn't handle them. Fix: add `elif action == 'replace': r = apply_replace(...)` to the dispatch.
- **2026-06-04 (caught in 4th run):** Cleanup reported 0 garbage because the multi-line rows didn't match the line-level pattern. Fix: `find_garbage_rows_in_text()` for row-level detection.
- **2026-06-04 (caught in 5th run):** The cleanup's line-level pass and multi-line pass ran in the wrong order, so multi-line detection never saw the rows the line-level pass created. Fix: run multi-line detection *after* line-level, with a re-scan loop.

## What NOT to do

- ⛔ `applied: true` without `verified_mutations` — lying log.
- ⛔ Skip diff-check on "small" writes — always check.
- ⛔ Silently drop skipped entries — log with reasons.
- ⛔ Hardcode `/opt/data/profiles/` — use `_lib.profiles_root()`.
- ⛔ Trust `set -e` in bash — verify each phase wrote its output with `if [ ! -s "$OUTPUT" ]` before chaining.
- ⛔ Write metadata-only entries — reject in `validate_proposal_format()`.
- ⛔ Skip the format validator — it's the only line of defense against the Actionable Instruction Principle violation.
- ⛔ Run cleanup without multi-line row detection — half the garbage is multi-line.

## Test it

Run the cycle on a profile with stale garbage. MEMORIZE should:
- Strip line-level spam (CROSS-CYCLE PATTERN rows)
- Strip multi-line malformed rows (Evolution Log rows with newline in action)
- Reject metadata-only proposals (return `format_invalid`)
- Validate every proposal's first line matches the file's format
- Diff-check every write (`sha_before != sha_after`)
- Log the cycle's verified mutations to a fresh `evol.jsonl`
- Back up the old log to `evol.jsonl.historical-{date}` if it exists
