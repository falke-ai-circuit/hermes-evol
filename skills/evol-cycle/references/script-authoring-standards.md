# Script Authoring Standards — evol-cycle Phase Scripts

> All six phase scripts under `phases/{absorb,reflect,adapt,explore,express,memorize}/scripts/*.py` follow the same contract. This is the contract. Bypassing it is a known failure mode.

## The contract

Every phase script must:

1. **Accept `target` (or `target_agent` for ABSORB) as a required positional argument.**
2. **Accept `-o / --output FILE` as an optional argument.** When given, write the full result to FILE. When absent, write to stdout.
3. **Exit with code 0 on success, non-zero on failure.** The bash orchestrator uses `set -euo pipefail`; a silent no-op that exits 0 is the worst kind of failure.
4. **Use `argparse`, not `sys.argv` index parsing.** `argparse` gives `--help` for free, validates types, and is greppable.
5. **Import everything you use.** When patching a script to add argparse, the `import argparse` line MUST be added in the same patch as the `argparse.ArgumentParser()` call. Do not assume the import is already there.
6. **Output pure JSON.** No ANSI colors, no progress bars, no `print()` debugging. The bash orchestrator pipes every output through `python -m json.tool` and any non-JSON noise breaks the chain.
7. **Read inputs strictly as JSON.** The previous phase's output is the input. If you can't parse it, exit non-zero with a clear stderr message.

## The bash orchestrator contract

`run.sh` in `skills/evol-cycle/` chains the six phase scripts. After every phase, it must:

```bash
"$PY" "$SCRIPT" "$INPUT" -o "$OUTPUT" || {
    echo "✗ Phase FAILED: $PHASE_NAME" >&2
    echo "  input:  $INPUT" >&2
    echo "  output: $OUTPUT (expected)" >&2
    exit 1
}

# Verify the output file actually exists and is non-empty
if [ ! -s "$OUTPUT" ]; then
    echo "✗ Phase produced no output: $PHASE_NAME" >&2
    exit 1
fi
```

**Do not** trust `set -e` alone. A script that writes nothing to `$OUTPUT` and exits 0 still produces a non-existent/empty file. Check `-s` (file exists AND size > 0) before chaining to the next phase.

## When a phase returns "no actionable changes"

**This is success, not failure.** The cycle ran end-to-end, found nothing to change, and produced a valid empty result. `run.sh` must:

- Print the empty-plan summary (0 actionable, 0 verified mutations)
- Exit with code 0
- NOT trigger any "cycle failed" alarm

The signal that the cycle is working correctly is that empty plans are reported as such, not hidden. A cycle that always produces mutations is suspicious — it means the diff-check is broken.

## Bug history (so we don't repeat these)

| Date | Bug | Fix | Where it bit |
|---|---|---|---|
| 2026-06-04 | `absorb/scripts/collect_state.py` ignored `-o` because it parsed `sys.argv[1]` and dropped everything after | Rewrite `main()` to use argparse and write to `args.output` if given | First end-to-end run of `run.sh`; output was missing, phase 2 crashed reading it |
| 2026-06-04 | `argparse.ArgumentParser()` call without `import argparse` in the same patch | Add `import argparse` to the import block in the same edit | First end-to-end run of `run.sh`; `NameError: name 'argparse' is not defined` |

## Reference implementation

Each phase script under `phases/*/scripts/` is the canonical example. When writing a new phase or modifying an existing one, match the existing scripts' structure exactly:

```python
#!/usr/bin/env python3
"""<PHASE_NAME> phase: <one-line description>.

Usage: <script_name>.py <required_args> [-o output.json]
"""
import argparse
import json
import sys
from pathlib import Path

def safe_load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as e:
        return {"_error": str(e)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input_json', help='path to previous phase output')
    ap.add_argument('-o', '--output', help='output file (default: stdout)')
    args = ap.parse_args()

    # ... work ...

    text = json.dumps(result, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(text)
    else:
        sys.stdout.write(text + '\n')
    sys.exit(0)

if __name__ == '__main__':
    main()
```

## Don't do

- Don't use `print()` for the result. Use `json.dump` or `json.dumps` then write.
- Don't read input via `json.loads(sys.stdin.read())`. The orchestrator uses file paths, not stdin.
- Don't add progress logging to stdout. The bash orchestrator captures stdout as JSON.
- Don't catch `Exception` broadly and `pass`. If something fails, propagate so `run.sh` can fail loudly.
- Don't write to `evol.jsonl` from any phase except `memorize`. MEMORIZE owns the audit log.

## Testing a script in isolation

```bash
# Test absorb
python phases/absorb/scripts/collect_state.py analyst | python -m json.tool | head -20

# Test reflect (needs absorb output as input)
python phases/absorb/scripts/collect_state.py analyst -o /tmp/absorb.json
python phases/reflect/scripts/pattern_graph.py /tmp/absorb.json | python -m json.tool | head -20

# Full chain
bash run.sh analyst
```

The `| python -m json.tool` after every command validates that the output is valid JSON. If it isn't, the script is wrong.
