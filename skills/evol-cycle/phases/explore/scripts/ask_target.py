#!/usr/bin/env python3
"""EXPLORE phase: external + agent deeper, *targeted by express's gap_vector*.

Usage: ask_target.py <absorb.json> <reflect.json> <express.json> [-o output.json]
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from _lib import profile_dir  # noqa: E402


def safe_load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as e:
        return {"_error": str(e)}


def web_search(query: str, limit: int = 3) -> list:
    searxng = os.environ.get('SEARXNG_URL', '').strip().rstrip('/')
    if not searxng:
        return []
    try:
        data = urllib.parse.urlencode({'q': query, 'format': 'json'}).encode()
        req = urllib.request.Request(
            f"{searxng}/search", data=data, method='POST',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            payload = json.loads(r.read())
        results = []
        for hit in (payload.get('results') or [])[:limit]:
            results.append({
                'url': hit.get('url', ''),
                'title': hit.get('title', ''),
                'snippet': hit.get('content', '')[:300],
                'relevance': hit.get('score', 0.0),
                'query_used': query,
            })
        return results
    except Exception as e:
        return [{'error': str(e)[:200], 'query_used': query}]


def write_pending_question(agent: str, question: str) -> dict:
    path = profile_dir(agent) / 'pending_questions.md'
    ts = datetime.now().isoformat(timespec='seconds')
    with path.open('a') as f:
        f.write(f"\n## {ts} (from EVOL explore)\n{question}\n")
    return {"status": "queued", "path": str(path)}


def compile_unanswered(express: dict, external: list) -> list:
    out = []
    if not external:
        out.append("Web search returned no usable results for express's gap_vector.")
    if express.get('voice') == 'ev_proxy':
        out.append("Target agent not active; express voice is a reconstruction, not a real voice.")
    if express.get('voice') == 'hybrid':
        out.append("Target agent active but subagent spawn failed; voice is partial.")
    return out[:5]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('absorb_json')
    ap.add_argument('reflect_json')
    ap.add_argument('express_json')
    ap.add_argument('-o', '--output')
    args = ap.parse_args()

    absorb = safe_load(Path(args.absorb_json))
    reflect = safe_load(Path(args.reflect_json))
    express = safe_load(Path(args.express_json))
    if not all([absorb, reflect, express]):
        print("ERROR: missing input(s)", file=sys.stderr)
        sys.exit(1)

    target = absorb.get('profile', 'unknown')

    # Primary queries: express's gap_vector
    primary_queries = express.get('gap_vector_for_explore', []) or []
    # Fallback queries: reflect's gaps (only if express gave nothing)
    if not primary_queries:
        primary_queries = reflect.get('gaps', []) or []
    if not primary_queries:
        primary_queries = [f"{target} {absorb.get('profile')} evolution patterns"]

    external = []
    queries_used = []
    for q in primary_queries[:3]:
        if not q or not isinstance(q, str):
            continue
        results = web_search(q, limit=2)
        if results:
            external.extend(results)
            queries_used.append(q)

    # Queue an express-shaped question to pending_questions for the agent
    express_opinion = express.get('opinion', '')
    if express_opinion:
        question = (
            f"EVOL is running a 6-phase cycle on you ({target}). "
            f"Express wrote in your voice: {express_opinion[:400]}... "
            f"What do you actually want to be different in your circuit files? "
            f"What capability or rule is missing?"
        )
        agent_perspective = write_pending_question(target, question)
    else:
        agent_perspective = {"status": "no_opinion", "reason": "express opinion empty"}

    unanswered = compile_unanswered(express, external)

    out = {
        'explore_ts': time.time(),
        'target': target,
        'queries_used': queries_used,
        'external': external,
        'agent_perspective': agent_perspective,
        'unanswered': unanswered,
    }

    text = json.dumps(out, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(text)
    else:
        print(text)


if __name__ == '__main__':
    main()
