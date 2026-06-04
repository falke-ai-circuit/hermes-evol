#!/usr/bin/env python3
"""REFLECT phase: build in-memory pattern graph, identify adjustment points.

Usage: pattern_graph.py /path/to/absorb_state.json [-o /path/to/output.json]

Reads absorb state, outputs reflect state. No LLM by default.
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

DOCTRINE_DENIAL_PATTERNS = re.compile(
    r'\b(cannot|must not|must never|is forbidden|is not allowed|no authority|runs in (suggested|active) mode)\b',
    re.IGNORECASE,
)


def safe_load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as e:
        return {"_error": str(e)}


def graphiti_search(query: str, num_results: int = 5) -> list:
    """Optional graphiti search. Silent skip if not configured."""
    try:
        from graphiti import graphiti_search as _g  # type: ignore
        return _g(query=query, num_results=num_results)
    except Exception:
        return []


def extract_patterns(evol_entries: list) -> list:
    """Aggregate patterns from evol entries, scoring by max weight and recency."""
    by_name = defaultdict(lambda: {
        'weight': 0.0, 'sources': [], 'evidence': [],
        'first_seen': float('inf'), 'last_seen': 0.0,
    })
    for entry in evol_entries:
        ts = entry.get('ts', entry.get('absorb_ts', 0.0)) or 0.0
        reflect = entry.get('reflect', {}) or {}
        for p in reflect.get('patterns', []) or []:
            if isinstance(p, str):
                name = p
                weight = 0.5
            else:
                name = p.get('name', p.get('pattern', str(p)))
                weight = float(p.get('weight', p.get('raw_weight', 0.5)) or 0.5)
            agg = by_name[name]
            agg['weight'] = max(agg['weight'], weight)
            agg['sources'].append(entry.get('cycle_id', entry.get('timestamp', 'unknown')))
            agg['evidence'].append(p.get('evidence', '') if isinstance(p, dict) else '')
            agg['first_seen'] = min(agg['first_seen'], ts) if ts else agg['first_seen']
            agg['last_seen'] = max(agg['last_seen'], ts) if ts else agg['last_seen']
    out = []
    for name, agg in by_name.items():
        out.append({
            'name': name,
            'weight': round(agg['weight'], 3),
            'sources': agg['sources'][:5],  # cap
            'evidence_count': len(agg['sources']),
            'first_seen': agg['first_seen'] if agg['first_seen'] != float('inf') else 0,
            'last_seen': agg['last_seen'],
        })
    out.sort(key=lambda p: -p['weight'])
    return out


def cluster_patterns(patterns: list) -> list:
    """Simple clustering by shared keywords. Deterministic, no LLM."""
    keywords = defaultdict(list)
    keyword_synonyms = {
        'identity': ['identity', 'self', 'soul', 'reflect_count'],
        'detection': ['detect', 'detect-without', 'detection-without', 'unresolved', 'logjam'],
        'doctrine': ['doctrine', 'practice', 'mandate', 'execute'],
        'isolation': ['isolation', 'signal', 'absorbed', 'cross-domain', 'silence'],
        'permission': ['permission', 'authority', 'write', 'access', 'autonomy'],
        'stale': ['stale', 'frozen', 'outdated', 'old'],
        'plugin': ['plugin', 'tool', 'broken', 'falkor'],
        'cycle': ['cycle', 'cooldown', 'acceleration', 'stuck'],
    }
    for p in patterns:
        n = p['name'].lower()
        for k, syns in keyword_synonyms.items():
            if any(s in n for s in syns):
                keywords[k].append(p['name'])
    clusters = []
    for k, members in keywords.items():
        if len(members) >= 2:
            avg_w = sum(next(p['weight'] for p in patterns if p['name'] == m) for m in members) / len(members)
            clusters.append({
                'name': f'{k}-cluster',
                'members': sorted(set(members)),
                'weight': round(avg_w, 3),
                'hypothesis': f'Patterns sharing keyword "{k}" may be the same failure in different words.',
            })
    return clusters


def check_stale_doctrine(doctrine_claims: list, circuit_files: dict) -> list:
    """For each denial-claim, search memory graph for a newer grant."""
    adjustments = []
    for claim in doctrine_claims:
        text = claim.get('text', '')
        if not DOCTRINE_DENIAL_PATTERNS.search(text):
            continue
        # Search graph for a grant that supersedes
        grant = graphiti_search(f'grants {text[:80]}', num_results=3)
        if grant:
            adjustments.append({
                'kind': 'stale_doctrine',
                'where': f'MEMORY.md line {claim["line"]}',
                'evidence': f'Doctrine: "{text[:120]}"\nGrant found in graph: {grant[0] if grant else "n/a"}',
                'weight': 0.85,
            })
    return adjustments


def check_recurring_orphans(patterns: list, memory_excerpt: str) -> list:
    """Pattern weight ≥ 0.85 with ≥3 sources AND no resolution note in MEMORY.md."""
    orphans = []
    for p in patterns:
        if p['weight'] < 0.85 or p['evidence_count'] < 3:
            continue
        if p['name'].lower() in memory_excerpt.lower():
            continue  # mentioned in MEMORY.md, not orphan
        orphans.append({
            'kind': 'recurring_orphan',
            'where': f'evol.jsonl pattern: {p["name"]}',
            'evidence': f'Weight {p["weight"]}, seen {p["evidence_count"]}x, not in MEMORY.md',
            'weight': 0.80,
        })
    return orphans


def check_pending_questions(pending: list) -> list:
    if not pending:
        return []
    # pending is now list of dicts: [{ts, origin, content}]
    lines = []
    for p in pending[-5:]:
        if isinstance(p, dict):
            lines.append(p.get('content', '')[:200])
        else:
            lines.append(str(p)[:200])
    return [{
        'kind': 'pending_question_unanswered',
        'where': 'pending_questions.md',
        'evidence': '\n'.join(lines),
        'weight': 0.90,
    }]


def check_missing_capability(doctrine_claims: list, pending: list) -> list:
    """Doctrine says "cannot do X" but pending questions ask for X."""
    out = []
    pending_strs = []
    for p in pending:
        if isinstance(p, dict):
            pending_strs.append(p.get('content', ''))
        else:
            pending_strs.append(str(p))
    for claim in doctrine_claims:
        text = claim.get('text', '').lower()
        if 'cannot' not in text and 'must not' not in text:
            continue
        # Look for capability requests in pending
        for q in pending_strs:
            ql = q.lower()
            if any(tok in ql for tok in text.split() if len(tok) > 5):
                out.append({
                    'kind': 'missing_capability',
                    'where': f"{claim['file']} line {claim['line']} vs pending_questions.md",
                    'evidence': f'Doctrine: "{text[:80]}"\nPending: "{q[:80]}"',
                    'weight': 0.88,
                })
    return out


def extract_anomalies(evol_entries: list) -> list:
    seen = set()
    out = []
    for e in evol_entries[-10:]:
        for a in (e.get('reflect', {}) or {}).get('anomalies', []) or []:
            if a in seen:
                continue
            seen.add(a)
            out.append(a)
    return out[:10]


def extract_gaps(adjustment_points: list, pending: list) -> list:
    """Questions only EXPLORE can answer (external knowledge needed)."""
    out = []
    for ap in adjustment_points:
        if ap['kind'] == 'stale_doctrine':
            out.append(f"What is the most recent grant for: {ap['evidence'][:60]}?")
        elif ap['kind'] == 'missing_capability':
            out.append(f"What capability was actually granted? (see {ap['where']})")
    if pending:
        out.append("Answer pending_questions.md items.")
    return out[:5]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('absorb_json', help='path to absorb state json')
    ap.add_argument('-o', '--output', help='output path (default: stdout)')
    args = ap.parse_args()

    state = safe_load(Path(args.absorb_json))
    if not state or state.get('_error'):
        print(f"ERROR: cannot read absorb state: {state}", file=sys.stderr)
        sys.exit(1)

    evol_entries = state.get('evol_entries', [])
    patterns = extract_patterns(evol_entries)
    clusters = cluster_patterns(patterns)
    doctrine = state.get('doctrine_claims', [])

    memory_excerpt = state.get('circuit_files', {}).get('MEMORY.md', {}).get('excerpt', '')
    pending = state.get('pending_questions', [])

    adjustment_points = []
    adjustment_points.extend(check_stale_doctrine(doctrine, state.get('circuit_files', {})))
    adjustment_points.extend(check_recurring_orphans(patterns, memory_excerpt))
    adjustment_points.extend(check_pending_questions(pending))
    adjustment_points.extend(check_missing_capability(doctrine, pending))
    adjustment_points.sort(key=lambda a: -a['weight'])

    anomalies = extract_anomalies(evol_entries)
    gaps = extract_gaps(adjustment_points, pending)

    out = {
        'reflect_ts': __import__('time').time(),
        'target': state.get('profile'),
        'patterns': patterns,
        'clusters': clusters,
        'adjustment_points': adjustment_points,
        'anomalies': anomalies,
        'gaps': gaps,
        'counts': {
            'patterns': len(patterns),
            'clusters': len(clusters),
            'adjustments': len(adjustment_points),
            'anomalies': len(anomalies),
            'gaps': len(gaps),
        },
    }

    text = json.dumps(out, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(text)
    else:
        print(text)


if __name__ == '__main__':
    main()
