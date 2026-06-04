#!/usr/bin/env python3
"""ABSORB phase: build the substrate for REFLECT.

Reads everything available about the target agent:
- circuit files (SOUL/AGENTS/MEMORY/IDENTITY) — current state
- evol.jsonl + evol.jsonl.historical-* — past EVOL activity (merged, historical flagged untrusted)
- session files — full session content: system_prompt (doctrine snapshot), messages (activity)
- pending_questions.md — questions for the agent
- kanban.db — recent tasks (if available)
- IDENTITY.md frontmatter — reflect_count, last_reflect, role

Builds:
- a temporal doctrine map: each session's system_prompt is a doctrine snapshot at a point in time
- an activity log: each session's message_count, duration, platform, model
- a unified evol history: all entries sorted by ts, with source flag (current/historical)
- the current circuit state

This is the substrate reflect operates on. Without it, reflect is hallucinating patterns.

Usage: collect_state.py <target_agent> [-o output.json]
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from _lib import profiles_root, profile_dir  # noqa: E402

CIRCUIT_FILES = ['SOUL.md', 'AGENTS.md', 'MEMORY.md', 'IDENTITY.md']

# Frontmatter pattern: ---\nrole: X\nlast_reflect: YYYY-MM-DD\nreflect_count: N\n---
FRONTMATTER_RE = re.compile(
    r'^---\s*\nrole:\s*(\S+)\s*\nlast_reflect:\s*(\S+)\s*\nreflect_count:\s*(\d+)\s*\n---',
    re.MULTILINE,
)

# Doctrine signals — keywords that indicate a doctrine section
DOCTRINE_HINT_RE = re.compile(
    r'^\s*[§#|].*?(?:doctrine|rule|gate|principle|mandate|protocol|standard|threshold|reflex)',
    re.IGNORECASE | re.MULTILINE,
)


def safe_read(path: Path, max_chars: int = 100_000) -> dict:
    if not path.exists():
        return {"path": str(path), "missing": True}
    try:
        text = path.read_text(errors='replace')
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[... truncated at {max_chars} chars, file is {len(text)} chars ...]"
        stat = path.stat()
        return {
            "path": str(path),
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "lines": text.count('\n') + 1,
            "content": text,
        }
    except Exception as e:
        return {"path": str(path), "corrupted": True, "error": str(e)}


def read_all_evolog(profile_dir_path: Path) -> list:
    """Read current evol.jsonl + all evol.jsonl.historical-*. Merge, historical flagged untrusted."""
    out = []
    # Historical first (older), then current
    files = sorted(profile_dir_path.glob('evol.jsonl.historical-*'))
    files.append(profile_dir_path / 'evol.jsonl')
    for f in files:
        if not f.exists():
            continue
        is_historical = '.historical' in f.name
        try:
            for line in f.read_text(errors='replace').splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    e['_source_file'] = f.name
                    e['untrusted'] = is_historical
                    out.append(e)
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
    # Sort by ts ascending; coerce to float safely
    def _ts(e):
        v = e.get('ts', e.get('timestamp', 0))
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0
    out.sort(key=_ts)
    return out


def read_sessions(profile_dir_path: Path, max_sessions: int = 50) -> list:
    """Read recent session files, extract activity + doctrine snapshots.

    Each session gives us:
    - session_id, start, end, duration
    - platform, model
    - message_count, role_distribution
    - system_prompt (doctrine snapshot at that time) — could be 50K chars
    - sample of recent messages
    """
    sess_dir = profile_dir_path / 'sessions'
    if not sess_dir.exists():
        return []
    files = sorted(sess_dir.glob('session_*.json*'),
                   key=lambda p: p.stat().st_mtime, reverse=True)[:max_sessions]
    out = []
    for f in files:
        try:
            if f.suffix == '.jsonl':
                # Newer format: one JSON per line
                lines = f.read_text(errors='replace').splitlines()
                if not lines:
                    continue
                try:
                    data = json.loads(lines[0])
                except json.JSONDecodeError:
                    continue
            else:
                data = json.loads(f.read_text(errors='replace'))
            stat = f.stat()
            sys_prompt = data.get('system_prompt') or ''
            messages = data.get('messages', [])
            role_counts = {}
            for m in messages:
                if isinstance(m, dict):
                    r = m.get('role', 'unknown')
                    role_counts[r] = role_counts.get(r, 0) + 1
            # Try to extract last_reflect + reflect_count from system_prompt
            fm_match = FRONTMATTER_RE.search(sys_prompt)
            fm_data = {}
            if fm_match:
                fm_data = {
                    'role': fm_match.group(1),
                    'last_reflect': fm_match.group(2),
                    'reflect_count_at_session': int(fm_match.group(3)),
                }
            # Doctrine signals — count occurrences of doctrine-hint lines
            doctrine_hits = len(DOCTRINE_HINT_RE.findall(sys_prompt))
            out.append({
                'session_id': data.get('session_id', f.stem),
                'path': str(f),
                'size': stat.st_size,
                'mtime': stat.st_mtime,
                'session_start': data.get('session_start'),
                'last_updated': data.get('last_updated'),
                'platform': data.get('platform'),
                'model': data.get('model'),
                'message_count': data.get('message_count', len(messages)),
                'role_counts': role_counts,
                'system_prompt_chars': len(sys_prompt),
                'doctrine_hints': doctrine_hits,
                'frontmatter': fm_data,
                'first_user_msg': next((m.get('content','')[:200] for m in messages if isinstance(m, dict) and m.get('role')=='user'), ''),
                'last_msg_preview': (messages[-1].get('content','')[:200] if messages and isinstance(messages[-1], dict) else ''),
            })
        except Exception as e:
            out.append({'path': str(f), 'corrupted': True, 'error': str(e)})
    return out


def read_pending(profile_dir_path: Path) -> list:
    p = profile_dir_path / 'pending_questions.md'
    if not p.exists():
        return []
    out = []
    section_re = re.compile(r'^##\s+(\S+)\s*(?:\(([^)]+)\))?\s*$', re.MULTILINE)
    matches = list(section_re.finditer(p.read_text(errors='replace')))
    if not matches:
        # Treat whole file as one pending question
        return [{'ts': None, 'origin': None, 'content': p.read_text(errors='replace').strip()}]
    for i, m in enumerate(matches):
        ts = m.group(1)
        origin = m.group(2) or None
        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(p.read_text(errors='replace'))
        content = p.read_text(errors='replace')[start:end].strip()
        out.append({'ts': ts, 'origin': origin, 'content': content})
    return out


def extract_doctrine_claims(circuit_files: dict) -> list:
    """Pull 'doctrine claims' from circuit files: lines starting with '§' or absolute-rule markers.

    These are the candidate statements for stale_doctrine detection.
    """
    out = []
    for f, info in circuit_files.items():
        if not info or info.get('missing') or not info.get('content'):
            continue
        for i, line in enumerate(info['content'].splitlines(), 1):
            stripped = line.strip()
            if not stripped:
                continue
            # § sections in MEMORY.md
            if stripped.startswith('§ '):
                out.append({'file': f, 'line': i, 'text': stripped[:300]})
            # Hard rule markers
            elif any(s in stripped.lower() for s in ['must not', 'cannot', 'forbidden', 'no authority', 'is not allowed', 'must never']):
                if len(stripped) < 300:
                    out.append({'file': f, 'line': i, 'text': stripped})
    return out


def build_activity_timeseries(sessions: list) -> dict:
    """From session metadata, build activity summary."""
    if not sessions:
        return {'total_sessions_read': 0, 'first': None, 'last': None, 'platforms': {}, 'models': {}}
    platforms = {}
    models = {}
    total_messages = 0
    doctrine_hint_total = 0
    for s in sessions:
        if s.get('corrupted'):
            continue
        p = s.get('platform', 'unknown')
        platforms[p] = platforms.get(p, 0) + 1
        m = s.get('model', 'unknown')
        models[m] = models.get(m, 0) + 1
        total_messages += s.get('message_count', 0)
        doctrine_hint_total += s.get('doctrine_hints', 0)
    return {
        'total_sessions_read': len(sessions),
        'first': sessions[-1].get('session_start') if sessions else None,
        'last': sessions[0].get('session_start') if sessions else None,
        'platforms': platforms,
        'models': models,
        'total_messages': total_messages,
        'doctrine_hint_total': doctrine_hint_total,
    }


def build_temporal_doctrine_map(sessions: list, current_circuit: dict) -> dict:
    """For each session, extract reflect_count from frontmatter. This is a temporal series
    showing how the agent's self-acknowledged evolution count grew over time."""
    series = []
    for s in sessions:
        if s.get('corrupted'):
            continue
        fm = s.get('frontmatter', {})
        if fm and 'reflect_count_at_session' in fm:
            series.append({
                'session_id': s['session_id'],
                'session_start': s.get('session_start'),
                'last_reflect': fm.get('last_reflect'),
                'reflect_count': fm['reflect_count_at_session'],
            })
    series.sort(key=lambda x: x.get('session_start') or '')
    current_count = None
    if 'IDENTITY.md' in current_circuit and not current_circuit['IDENTITY.md'].get('missing'):
        m = FRONTMATTER_RE.search(current_circuit['IDENTITY.md'].get('content', ''))
        if m:
            current_count = {
                'last_reflect': m.group(2),
                'reflect_count': int(m.group(3)),
            }
    return {
        'series': series[-20:],  # last 20 sessions
        'current': current_count,
        'drift': (
            series[-1]['reflect_count'] - current_count['reflect_count']
            if current_count and series
            else None
        ),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('target_agent', help='profile name to absorb')
    ap.add_argument('-o', '--output', help='output file (default: stdout)')
    ap.add_argument('--max-sessions', type=int, default=50, help='max sessions to read (default 50)')
    ap.add_argument('--max-content-chars', type=int, default=100_000, help='per-file max chars')
    args = ap.parse_args()
    target = args.target_agent

    try:
        pdir = profile_dir(target)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # 1. Circuit files — current state
    circuit = {}
    for f in CIRCUIT_FILES:
        circuit[f] = safe_read(pdir / f, max_chars=args.max_content_chars)

    # 2. Identity frontmatter
    identity_fm = {}
    if 'IDENTITY.md' in circuit and not circuit['IDENTITY.md'].get('missing'):
        m = FRONTMATTER_RE.search(circuit['IDENTITY.md'].get('content', ''))
        if m:
            identity_fm = {
                'role': m.group(1),
                'last_reflect': m.group(2),
                'reflect_count': int(m.group(3)),
            }

    # 3. EVOL history (current + historical, merged)
    evol_entries = read_all_evolog(pdir)

    # 4. Sessions — full content of recent N
    sessions = read_sessions(pdir, max_sessions=args.max_sessions)

    # 5. Pending questions
    pending = read_pending(pdir)

    # 6. Doctrine claims
    doctrine_claims = extract_doctrine_claims(circuit)

    # 7. Activity timeseries
    activity = build_activity_timeseries(sessions)

    # 8. Temporal doctrine map
    temporal = build_temporal_doctrine_map(sessions, circuit)

    state = {
        'profile': target,
        'profile_dir': str(pdir),
        'absorb_ts': time.time(),
        'identity_frontmatter': identity_fm,
        'circuit_files': circuit,
        'doctrine_claims': doctrine_claims,
        'evol_entries': evol_entries,
        'evol_entries_count': len(evol_entries),
        'sessions': sessions,
        'sessions_count_read': len(sessions),
        'activity': activity,
        'temporal_doctrine': temporal,
        'pending_questions': pending,
        'pending_questions_count': len(pending),
        'falkordb_graphs': [],  # left for optional probe
    }

    text = json.dumps(state, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(text)
    else:
        sys.stdout.write(text + '\n')
    sys.exit(0)


if __name__ == '__main__':
    main()
