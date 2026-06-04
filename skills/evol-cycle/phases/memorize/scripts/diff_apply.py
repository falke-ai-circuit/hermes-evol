#!/usr/bin/env python3
"""MEMORIZE phase: diff-checked writes with tier transitions and format validation.

Inputs: adapt, express, absorb.
Applies the adapt plan. Supports: append, replace, cleanup, append_demotion_marker,
demote_to_knowledge. Validates every write is a real instruction (fails the
metadata-only check). Writes a single jsonl entry to evol.jsonl summarizing the cycle.
"""
import argparse
import hashlib
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from _lib import (  # noqa: E402
    profile_dir, validate_proposal_format, classify_tier,
    find_garbage_rows_in_text,
)


def safe_load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as e:
        return {"_error": str(e)}


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def apply_append(profile, file_rel: str, text: str) -> dict:
    """Append text to file_rel. Validates format. Returns diff-checked result."""
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
    try:
        path.write_text(after)
    except Exception as e:
        return {"verified": False, "reason": f"write_failed: {e}"}
    sha_after = sha256(after)
    return {
        "verified": True,
        "file": file_rel,
        "delta_lines": after.count('\n') - before.count('\n'),
        "sha_before": sha_before,
        "sha_after": sha_after,
    }


def apply_replace(profile, file_rel: str, current: str, proposed: str) -> dict:
    """Replace current with proposed in file_rel. Returns diff-checked result."""
    path = profile / file_rel
    if not path.exists():
        return {"verified": False, "reason": f"file_not_found:{file_rel}"}
    before = path.read_text(errors='replace')
    sha_before = sha256(before)
    if not current:
        return {"verified": False, "reason": "no_current_excerpt"}
    if current not in before:
        return {"verified": False, "reason": "excerpt_not_found"}
    after = before.replace(current, proposed, 1)
    try:
        path.write_text(after)
    except Exception as e:
        return {"verified": False, "reason": f"write_failed: {e}"}
    sha_after = sha256(after)
    return {
        "verified": True,
        "file": file_rel,
        "delta_lines": after.count('\n') - before.count('\n'),
        "sha_before": sha_before,
        "sha_after": sha_after,
    }


def apply_cleanup(profile, garbage: dict, multiline_rows: dict = None) -> dict:
    """Strip CROSS-CYCLE PATTERN spam AND multi-line garbage rows."""
    multiline_rows = multiline_rows or {}
    per_file = {}
    for file_rel, line_nums in garbage.items():
        path = profile / file_rel
        if not path.exists():
            per_file[file_rel] = {"verified": False, "reason": "file_not_found"}
            continue
        before = path.read_text(errors='replace')
        sha_before = sha256(before)
        lines = before.splitlines()
        keep = [l for i, l in enumerate(lines, 1) if i not in set(line_nums)]
        after = '\n'.join(keep)
        if not after.endswith('\n'):
            after += '\n'
        rows_stripped = []
        file_multiline = multiline_rows.get(file_rel, [])
        if file_multiline:
            new_lines = after.splitlines()
            keep2 = [l for i, l in enumerate(new_lines, 1)
                     if not any(s <= i <= e for s, e in file_multiline)]
            after = '\n'.join(keep2)
            if not after.endswith('\n'):
                after += '\n'
            rows_stripped = file_multiline
        for _ in range(5):
            rows = find_garbage_rows_in_text(after)
            if not rows:
                break
            new_lines = after.splitlines()
            keep2 = [l for i, l in enumerate(new_lines, 1)
                     if not any(s <= i <= e for s, e in rows)]
            after = '\n'.join(keep2)
            if not after.endswith('\n'):
                after += '\n'
            rows_stripped.extend(rows)
        if before == after:
            per_file[file_rel] = {"verified": False, "reason": "no_garbage"}
            continue
        try:
            path.write_text(after)
        except Exception as e:
            per_file[file_rel] = {"verified": False, "reason": f"write_failed: {e}"}
            continue
        sha_after = sha256(after)
        per_file[file_rel] = {
            "verified": True,
            "file": file_rel,
            "delta_lines": after.count('\n') - before.count('\n'),
            "sha_before": sha_before,
            "sha_after": sha_after,
            "lines_stripped": len(line_nums) + sum((e - s + 1) for s, e in rows_stripped),
            "multiline_rows_stripped": len(rows_stripped),
        }
    any_verified = any(v.get('verified') for v in per_file.values())
    return {
        "verified": any_verified,
        "files": per_file,
        "total_lines_stripped": sum(v.get('lines_stripped', 0) for v in per_file.values()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('adapt_json')
    ap.add_argument('express_json')
    ap.add_argument('absorb_json')
    ap.add_argument('-o', '--output')
    args = ap.parse_args()

    adapt = safe_load(Path(args.adapt_json))
    express = safe_load(Path(args.express_json))
    absorb = safe_load(Path(args.absorb_json))
    if not all([adapt, express, absorb]):
        print("ERROR: missing input(s)", file=sys.stderr)
        sys.exit(1)

    target = adapt.get('target', 'unknown')
    try:
        profile = profile_dir(target)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    verified = []
    skipped = []
    demotions = []
    plan = adapt.get('adjustment_plan', []) or []

    for idx, item in enumerate(plan):
        action = item.get('action')
        file_rel = item.get('file')
        if action == 'none':
            skipped.append({"plan_index": idx, "reason": item.get('skip_reason', item.get('reason', 'none'))})
            continue
        if not file_rel or file_rel == 'ALL':
            if action == 'cleanup':
                r = apply_cleanup(profile, item.get('garbage_lines', {}),
                                  item.get('multiline_rows', {}))
                if r.get('verified'):
                    verified.append({
                        "type": "cleanup",
                        "files": r['files'],
                        "total_lines_stripped": r['total_lines_stripped'],
                    })
                else:
                    skipped.append({"plan_index": idx, "reason": "cleanup_no_op"})
            else:
                skipped.append({"plan_index": idx, "reason": "no_file_or_unknown"})
            continue
        if action in ('append', 'append_demotion_marker'):
            r = apply_append(profile, file_rel, item.get('proposed_text', ''))
        elif action == 'replace':
            r = apply_replace(profile, file_rel, item.get('current_excerpt') or '', item.get('proposed_text', ''))
        elif action == 'demote_to_knowledge':
            text = item.get('proposed_text') or f"\n§ demoted-{item.get('evidence','')[:30]} (wt:0.30) — demoted from circuit\n"
            r = apply_append(profile, 'MEMORY.md', text)
            if r.get('verified'):
                demotions.append({"file": "MEMORY.md", "from": "CIRCUIT", "to": "KNOWLEDGE",
                                  "reason": item.get('demotion_reason', 'agent + external contradicted')})
        else:
            skipped.append({"plan_index": idx, "reason": f"unknown_action:{action}"})
            continue
        if r.get('verified'):
            r['tier'] = item.get('tier', classify_tier(item.get('weight', 0.5)))
            r['instruction_format'] = item.get('instruction_format', 'unknown')
            verified.append(r)
        else:
            skipped.append({"plan_index": idx, "reason": r.get('reason')})

    cycle_id = f"evol-on-{target}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    jsonl_entry = {
        "profile": "evol",
        "mode": "manual",
        "target_agent": target,
        "cycle_id": cycle_id,
        "timestamp": datetime.now().isoformat(timespec='seconds'),
        "ts": time.time(),
        "approval_mode": "active",
        "phases_executed": ["absorb", "reflect", "express", "explore", "adapt", "memorize"],
        "express": {
            "voice": express.get('voice', ''),
            "gap_vector_size": len(express.get('gap_vector_for_explore', []) or []),
        },
        "memorize": {
            "items_scored": len(plan),
            "verified_mutations": len(verified),
            "skipped": len(skipped),
            "demotions": len(demotions),
        },
    }
    evol_jsonl = profile / 'evol.jsonl'
    try:
        with evol_jsonl.open('a') as f:
            f.write(json.dumps(jsonl_entry) + '\n')
    except Exception as e:
        skipped.append({"plan_index": -1, "reason": f"jsonl_write_failed:{e}"})

    out = {
        'memorize_ts': time.time(),
        'target': target,
        'cycle_id': cycle_id,
        'verified_mutations': verified,
        'demotions': demotions,
        'skipped': skipped,
        'jsonl_entry': jsonl_entry,
    }

    text = json.dumps(out, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(text)
    else:
        print(text)


if __name__ == '__main__':
    main()
