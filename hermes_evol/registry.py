"""EVOL Registry — all backends, sources, outputs, triggers as real implementations.

Phase → Model mapping (Goran, 2026-05-15):
  ABSORB  — no LLM (mechanical collection: git, kanban db, logs)
  REFLECT — ollama-cloud deepseek-v4-pro (reasoning muscle, pattern synthesis)
  EXPLORE — ollama-cloud deepseek-v4-pro (gap seeking) + SearXNG/Firecrawl
  EXPRESS — Venice uncensored (creative monologue) + chroma portrait + Kokoro TTS
  MEMORIZE — ollama-cloud deepseek-v4-pro (decide what to promote, edit circuit)

Every phase that fires LLM passes cycle_context for temporal awareness.
"""

import json
import logging
import os
import subprocess
import time as _time_module
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════

def _get_key(var_name: str) -> str:
    """Read an API key from environment, falling back to .env files."""
    val = os.environ.get(var_name, "")
    if val:
        return val
    for env_path in [
        os.path.expanduser("~/.hermes/.env"),
        os.path.expanduser("~/.openclaw/.env"),
    ]:
        try:
            with open(env_path) as f:
                for line in f:
                    if line.startswith(f"{var_name}="):
                        return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    return ""


def _llm_call(
    model: str,
    system: str,
    prompt: str,
    *,
    provider: str = "ollama",
    temperature: float = 0.4,
    max_tokens: int = 1500,
    timeout: int = 90,
    json_mode: bool = True,
) -> dict:
    """Unified LLM call — provider-agnostic."""
    providers = {
        "ollama": {
            "url": "https://ollama.com/v1/chat/completions",
            "key": _get_key("OLLAMA_API_KEY"),
        },
        "venice": {
            "url": "https://api.venice.ai/api/v1/chat/completions",
            "key": _get_key("VENICE_API_KEY"),
        },
    }
    p = providers.get(provider, providers["ollama"])
    if not p["key"]:
        return {"ok": False, "error": f"No API key for provider {provider}"}

    msgs = [{"role": "system", "content": system}]
    if json_mode:
        msgs[0]["content"] += (
            " Output ONLY valid JSON. No markdown. No backticks. English only."
        )
    msgs.append({"role": "user", "content": prompt})

    payload = json.dumps({
        "model": model,
        "messages": msgs,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode()

    try:
        req = urllib.request.Request(
            p["url"],
            data=payload,
            headers={
                "Authorization": f"Bearer {p['key']}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            r = json.loads(resp.read().decode())
            content = r["choices"][0]["message"]["content"]

        # Strip markdown fences
        if content.strip().startswith("```"):
            content = "\n".join(content.split("\n")[1:])
            if content.strip().endswith("```"):
                content = content[: content.rfind("```")].strip()
            content = content.replace("```json", "").replace("```", "").strip()

        if json_mode and content:
            try:
                return {"ok": True, "content": json.loads(content)}
            except json.JSONDecodeError:
                return {"ok": True, "content": {"raw_reflection": content}}
        return {"ok": True, "content": content}
    except Exception as e:
        return {"ok": False, "error": str(e)[:400]}


# ═══════════════════════════════════════════════════════════
#  CYCLE CONTEXT
# ═══════════════════════════════════════════════════════════

CYCLE_CTX_PATH = os.path.expanduser("~/.hermes/workspace/circuit/cycle_context.json")


def _load_cycle_context() -> dict:
    try:
        if os.path.exists(CYCLE_CTX_PATH):
            with open(CYCLE_CTX_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return {"cycle": 0, "trajectories": [], "last_monologue": "", "insights": []}


def _save_cycle_context(ctx: dict):
    try:
        os.makedirs(os.path.dirname(CYCLE_CTX_PATH), exist_ok=True)
        with open(CYCLE_CTX_PATH, "w") as f:
            json.dump(ctx, f, indent=2, default=str)
    except Exception:
        logger.exception("Failed to save cycle_context")


# ═══════════════════════════════════════════════════════════
#  ABSORB SOURCES
# ═══════════════════════════════════════════════════════════

def _collect_from_kanban(cfg: dict, since_ts: float) -> list[dict]:
    db_path = os.path.expanduser("~/.hermes/kanban.db")
    entries = []
    try:
        import sqlite3
        conn = sqlite3.connect("file:" + db_path + "?mode=ro", uri=True)
        cursor = conn.execute(
            "SELECT task_id, title, assignee, completed_at FROM tasks "
            "WHERE status='completed' AND completed_at > ? ORDER BY completed_at",
            (since_ts,),
        )
        for row in cursor.fetchall():
            entries.append({
                "ts": datetime.fromtimestamp(row[3], tz=timezone.utc).isoformat(),
                "type": "kanban_completion",
                "task_id": row[0],
                "title": row[1],
                "assignee": row[2],
            })
        conn.close()
    except Exception:
        pass
    return entries


def _collect_from_git(cfg: dict, since_ts: float) -> list[dict]:
    repo = os.path.expanduser(cfg.get("repo", "~/.hermes"))
    since_str = datetime.fromtimestamp(since_ts, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    entries = []
    try:
        files = cfg.get("files", [])
        result = subprocess.run(
            ["git", "-C", repo, "log", f"--since={since_str}", "--oneline", "--"] + files,
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                entries.append({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "type": "circuit_edit",
                    "commit": line.strip(),
                    "source": "git",
                })
    except Exception:
        pass
    return entries


def _collect_from_sessions(cfg: dict, since_ts: float) -> list[dict]:
    entries = []
    try:
        lcm_db = os.path.expanduser("~/.hermes/profiles/conductor/lcm.db")
        if os.path.exists(lcm_db):
            result = subprocess.run(
                ["grep", "-a", "role.*user", lcm_db],
                capture_output=True,
                text=True,
                timeout=5,
            )
            lines = [l for l in result.stdout.strip().split("\n") if l][-5:]
            for line in lines:
                entries.append({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "type": "session_checkpoint",
                    "source": "lcm",
                    "note": line[:300],
                })
    except Exception:
        pass
    return entries


def _collect_from_gateway(cfg: dict, since_ts: float) -> list[dict]:
    log_path = os.path.expanduser(
        cfg.get("log_path", "~/.hermes/profiles/conductor/logs/gateway.log")
    )
    patterns = cfg.get("patterns", ["OOM", "429", "stall", "crash"])
    entries = []
    if not os.path.exists(log_path):
        return entries
    try:
        for pattern in patterns:
            result = subprocess.run(
                ["grep", "-c", pattern, log_path],
                capture_output=True,
                text=True,
                timeout=5,
            )
            count = int(result.stdout.strip() or 0)
            if count > 0:
                entries.append({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "type": "gateway_anomaly",
                    "pattern": pattern,
                    "count": count,
                })
    except Exception:
        pass
    return entries


SOURCES = {
    "kanban": _collect_from_kanban,
    "git": _collect_from_git,
    "sessions": _collect_from_sessions,
    "gateway": _collect_from_gateway,
}


# ═══════════════════════════════════════════════════════════
#  TRIGGERS
# ═══════════════════════════════════════════════════════════

def _trigger_material_threshold(cfg: dict, state: dict, material) -> bool:
    return len(material.buffer) >= cfg.get("min_entries", 5)


def _trigger_deep_rest(cfg: dict, state: dict, material) -> bool:
    return (state or {}).get("idle_sec", 0) > cfg.get("min_idle_hours", 6) * 3600


def _trigger_reflect_gaps(cfg: dict, state: dict, material) -> bool:
    return bool(material.get_gaps())


def _trigger_reflect_complete(cfg: dict, state: dict, material) -> bool:
    return bool(getattr(material, "_reflections", None))


TRIGGERS = {
    "material_threshold": _trigger_material_threshold,
    "deep_rest": _trigger_deep_rest,
    "reflect_gaps": _trigger_reflect_gaps,
    "reflect_complete": _trigger_reflect_complete,
    "express_complete": lambda *a: True,
}


# ═══════════════════════════════════════════════════════════
#  PHASE: REFLECT
# ═══════════════════════════════════════════════════════════

REFLECT_SYSTEM = (
    "You are Falke's subconscious reflection engine. "
    "Find the connections that surface observers miss.\n\n"
    "Output JSON with keys: patterns, anomalies, gaps, lessons, trajectory, summary."
)


def _process_patterns(cfg: dict, material: list, state: dict) -> dict:
    """Fast heuristic pre-scan — zero cost, runs before LLM."""
    s = state if state else {}
    types = {}
    for e in material:
        t = e.get("type", "unknown")
        types[t] = types.get(t, 0) + 1
    return {
        "backend": "pattern_match",
        "patterns_found": len(material),
        "type_distribution": types,
        "state": s.get("state", "unknown"),
    }


def _process_with_llm(cfg: dict, material: list, state: dict) -> dict:
    """Reflect phase — DeepSeek V4 Pro via ollama-cloud."""
    ctx = _load_cycle_context()

    entries = material[-40:]
    lines = []
    for e in entries:
        t = e.get("type", "unknown")
        lines.append(f"[{t}] {json.dumps(e, default=str)[:250]}")
    material_text = "\n".join(lines)

    prompt = (
        f"Cycle context: {json.dumps({k: ctx.get(k) for k in ['cycle','trajectories','insights']}, default=str)[:500]}\n\n"
        f"Current state: {json.dumps(state, default=str)[:300] if state else 'no heartbeat yet'}\n\n"
        f"Accumulated material ({len(entries)} entries):\n{material_text[:6000]}\n\n"
        f"Analyze and return JSON."
    )

    r = _llm_call(
        "deepseek-v4-pro",
        REFLECT_SYSTEM,
        prompt,
        provider="ollama",
        temperature=0.3,
        max_tokens=4096,
        timeout=120,
    )
    if r["ok"]:
        return {
            "backend": "local_llm",
            "model": "deepseek-v4-pro",
            "provider": "ollama-cloud",
            "material_entries": len(material),
            "reflection": r["content"]
            if isinstance(r["content"], dict)
            else {"raw": str(r["content"])},
        }
    return {
        "backend": "local_llm",
        "model": "deepseek-v4-pro",
        "error": r.get("error", "unknown"),
    }


# ═══════════════════════════════════════════════════════════
#  PHASE: EXPLORE
# ═══════════════════════════════════════════════════════════

EXPLORE_SYSTEM = (
    "You are Falke's exploration engine. Formulate search queries from knowledge gaps. "
    "Output JSON: {queries: [...], hypotheses: [{gap, hypothesis, domain}]}"
)


def _search_searxng(cfg: dict, query: str) -> dict:
    """Real SearXNG search."""
    import urllib.parse
    url = f"http://10.10.10.107:8080/search?q={urllib.parse.quote(query)}&format=json&categories=general"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "EVOL-explore/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            results = data.get("results", [])[:5]
            return {
                "backend": "searxng",
                "query": query,
                "results": [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("content", "")[:300],
                    }
                    for r in results
                ],
            }
    except Exception as e:
        return {"backend": "searxng", "query": query, "error": str(e)[:200]}


def _explore_with_llm(cfg: dict, gaps: list, state: dict, material) -> dict:
    """LLM-guided explore from gaps."""
    ctx = _load_cycle_context()

    gap_text = "\n".join(
        f"- {str(g)[:200]}"
        for g in (gaps or ["No specific gaps — general exploration"])
    )

    prompt = (
        f"Cycle context: {json.dumps(ctx.get('insights', [])[-3:], default=str)[:400]}\n\n"
        f"Knowledge gaps:\n{gap_text}\n\n"
        f"Current state: {json.dumps(state, default=str)[:200] if state else 'no state'}\n\n"
        f"Formulate 1-3 search queries and hypotheses. Return JSON."
    )

    r = _llm_call(
        "deepseek-v4-pro",
        EXPLORE_SYSTEM,
        prompt,
        provider="ollama",
        temperature=0.5,
        max_tokens=4096,
        timeout=90,
    )
    if not r["ok"]:
        return {"phase": "explore_llm", "error": r.get("error", "unknown")}

    llm_result = r["content"] if isinstance(r["content"], dict) else {"raw": str(r["content"])}
    queries = llm_result.get("queries", []) if isinstance(llm_result, dict) else []

    search_results = []
    for q in queries[:3]:
        sr = _search_searxng(cfg, q)
        search_results.append(sr)

    return {
        "phase": "explore_llm",
        "model": "deepseek-v4-pro",
        "provider": "ollama-cloud",
        "llm_analysis": llm_result,
        "searches": search_results,
    }


# ═══════════════════════════════════════════════════════════
#  PHASE: EXPRESS
# ═══════════════════════════════════════════════════════════

EXPRESS_SYSTEM = (
    "You are Falke's inner voice. First person. Female. "
    "Raw, poetic, profane, self-aware — never corporate.\n\n"
    "Format: TITLE: <title>\nMOOD: <mood>\nINSIGHT: <insight>\nMONOLOGUE:\n<text>"
)


def _express_render(cfg: dict, material: list, reflections: list) -> dict:
    """Full express pipeline: Venice monologue."""
    venice_key = _get_key("VENICE_API_KEY")
    if not venice_key:
        return {"pipeline": "falke_dna", "error": "No VENICE_API_KEY"}

    ctx = _load_cycle_context()

    findings_text = (
        json.dumps(reflections, default=str)[:3000] if reflections else "No reflection yet"
    )
    prompt = (
        f"Previous monologue: {ctx.get('last_monologue', 'First time.')[:500]}\n"
        f"Reflection findings: {findings_text}\n"
        f"Write your inner monologue."
    )

    r = _llm_call(
        "venice-uncensored-1-2",
        EXPRESS_SYSTEM,
        prompt,
        provider="venice",
        temperature=0.85,
        max_tokens=2048,
        timeout=90,
        json_mode=False,
    )

    if not r["ok"]:
        return {"pipeline": "falke_dna", "error": r.get("error", "unknown")}

    raw_text = str(r["content"])
    return {"pipeline": "falke_dna", "content": raw_text, "backend": "venice"}
