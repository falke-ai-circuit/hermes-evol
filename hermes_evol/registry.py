"""
EVOL Registry — Universal 5-Phase Engine.

Profile-aware absorb → reflect → explore → express → memorize cycle.
Supports per-phase model configuration via EvolConfig.
Circuit editing with auto/suggested/readonly modes.
Global mode: scan all profiles, aggregate into one cycle.

Architecture:
  gather side (data in):    absorb → reflect → explore
  output side (action out): express → memorize
"""

import json
import hashlib
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

# Relative import for plugin context, absolute fallback for standalone testing
try:
    from .config import EvolConfig, PhaseModelConfig, PROVIDER_ENDPOINTS
except ImportError:
    from config import EvolConfig, PhaseModelConfig, PROVIDER_ENDPOINTS  # type: ignore


def _http_get_json_raw(url, params=None, headers=None, timeout=30):
    """GET with params dict, returns response-like dict with .status_code and .json()."""
    import urllib.request as ur
    if params:
        qs = '&'.join(f'{urllib.parse.quote(k)}={urllib.parse.quote(str(v))}' for k,v in params.items())
        url = f'{url}?{qs}'
    req = ur.Request(url, headers=headers or {})
    try:
        with ur.urlopen(req, timeout=timeout) as resp:
            return {'status_code': resp.status, 'json': lambda: json.loads(resp.read().decode())}
    except Exception as e:
        return {'status_code': 999, 'json': lambda: {'_error': str(e)}}

def _http_post_json_raw(url, json=None, headers=None, timeout=30):
    """POST with json dict, returns response-like dict."""
    import urllib.request as ur
    body = j.dumps(json).encode() if json else b''
    req = ur.Request(url, data=body, headers=headers or {})
    try:
        with ur.urlopen(req, timeout=timeout) as resp:
            return {'status_code': resp.status, 'json': lambda: j.loads(resp.read().decode())}
    except Exception as e:
        return {'status_code': 999, 'json': lambda: {'_error': str(e)}}

# ── Internal HTTP helper (stdlib only, no external deps) ──

import urllib.request
import urllib.error
import urllib.parse

def _http_post_json(url: str, data: dict, headers: dict = None, timeout: int = 120) -> dict:
    """POST JSON to a URL, return parsed JSON response. Uses stdlib urllib."""
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}", "_body": e.read().decode("utf-8", errors="replace")[:500]}
    except Exception as e:
        return {"_error": str(e)}


def _http_get_json(url: str, headers: dict = None, timeout: int = 30) -> dict:
    """GET JSON from a URL. Uses stdlib urllib."""
    req_headers = {}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}", "_body": e.read().decode("utf-8", errors="replace")[:500]}
    except Exception as e:
        return {"_error": str(e)}


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _ts() -> float:
    return time.time()

def _hash(text: str, length: int = 12) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:length]

def _safe_read(path: str, default: str = "") -> str:
    """Read a file, return empty string on failure."""
    try:
        return Path(path).read_text()
    except (OSError, UnicodeDecodeError):
        return default

def _safe_json(path: str, default: Any = None) -> Any:
    """Read a JSON file, return default on failure."""
    try:
        return json.loads(Path(path).read_text())
    except (json.JSONDecodeError, OSError):
        return default if default is not None else {}

def _safe_write(path: str, content: str):
    """Write a file, create parents, silent on failure."""
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    except OSError:
        pass


def _call_llm(
    prompt: str,
    phase_config: PhaseModelConfig,
    cfg,  # EvolConfig — for provider URL resolution
    system_prompt: str = "",
    max_tokens: int = 4096,
) -> str:
    """
    Call an LLM using the phase's model configuration.
    Provider → endpoint resolved via PROVIDER_ENDPOINTS in config.
    Zero gateway dependency — direct API calls only.
    Returns raw text response.
    """
    provider = phase_config.provider or "venice"
    model = phase_config.model or "deepseek-v4-pro"
    api_key = phase_config.api_key

    # Resolve API key from environment (provider-aware)
    if not api_key:
        endpoint = PROVIDER_ENDPOINTS.get(provider, {})
        key_env = endpoint.get("api_key_env", "")
        if key_env:
            api_key = os.environ.get(key_env, "")
    if not api_key:
        # Broad fallback
        for env_var in ["OLLAMA_API_KEY", "VENICE_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"]:
            api_key = os.environ.get(env_var, "")
            if api_key:
                break

    temperature = phase_config.temperature
    actual_max_tokens = phase_config.max_tokens or max_tokens

    # Resolve base URL from config's provider mapping
    base_url = cfg.get_provider_url(provider) if cfg else ""
    if not base_url:
        endpoint = PROVIDER_ENDPOINTS.get(provider, {})
        base_url = endpoint.get("base_url", "")

    if not base_url:
        return f"[evol error: unknown provider '{provider}' — add to PROVIDER_ENDPOINTS]"

    chat_url = f"{base_url.rstrip('/')}/chat/completions"

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    data = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": actual_max_tokens,
    }

    # Venice-specific: GLM heretic needs venice_parameters
    if provider == "venice":
        data["venice_parameters"] = {"include_venice_system_prompt": False}

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    result = _http_post_json(chat_url, data, headers=headers, timeout=300)

    if "_error" in result:
        return f"[{provider} error: {result['_error']}]"

    try:
        msg = result["choices"][0]["message"]
        content = msg.get("content", "")
        if not content:
            content = msg.get("reasoning_content", "")
        return content or f"[{provider} error: empty response]"
    except (KeyError, IndexError, TypeError):
        return f"[{provider} error: unexpected response shape]"


def _call_venice(prompt, model, api_key, system, temp, max_tok) -> str:
    """Call Venice AI API (uncensored). Uses stdlib urllib.
    GLM heretic model: thinking + content share token budget — allocate enough for both."""
    url = "https://api.venice.ai/api/v1/chat/completions"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    # GLM heretic needs extra headroom: thinking burns tokens before content appears
    actual_max = max(max_tok, 4096)
    data = {
        "model": model or "olafangensan-glm-4.7-flash-heretic",
        "messages": messages,
        "temperature": temp,
        "max_tokens": actual_max,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    result = _http_post_json(url, data, headers=headers, timeout=120)
    if "_error" in result:
        return f"[venice error: {result['_error']}]"
    try:
        msg = result["choices"][0]["message"]
        content = msg.get("content", "")
        if not content:
            content = msg.get("reasoning_content", "")
        if not content:
            return f"[venice error: empty response (thinking consumed all {actual_max} tokens)]"
        return content
    except (KeyError, IndexError):
        return f"[venice error: unexpected response shape]"


def _call_ollama(prompt, model, system, temp, max_tok) -> str:
    """Call local Ollama. Uses stdlib urllib."""
    url = os.environ.get("OLLAMA_HOST", "http://ollama:11434") + "/api/generate"
    data = {
        "model": model,
        "prompt": f"{system}\n\n{prompt}" if system else prompt,
        "stream": False,
        "options": {"temperature": temp, "num_predict": max_tok},
    }
    result = _http_post_json(url, data, timeout=300)
    if "_error" in result:
        return f"[ollama error: {result['_error']}]"
    return result.get("response", "")


def _call_hermes_api(prompt, model, api_key, system, temp, max_tok) -> str:
    """Call Hermes gateway's OpenAI-compatible endpoint. Uses stdlib urllib."""
    url = os.environ.get("HERMES_API_URL", "http://localhost:8642") + "/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    data = {
        "model": model or "default",
        "messages": messages,
        "temperature": temp,
        "max_tokens": max_tok,
    }
    result = _http_post_json(url, data, headers=headers, timeout=300)
    if "_error" in result:
        return f"[hermes api error: {result['_error']}]"
    try:
        return result["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return f"[hermes api error: unexpected response shape]"


# ═══════════════════════════════════════════════════════════════════
# ABSORB — Gather context from profile sources
# ═══════════════════════════════════════════════════════════════════

def absorb(cfg: EvolConfig) -> Dict[str, Any]:
    """
    Gather all available context for the EVOL cycle.

    Returns:
        {
            "profile": str,
            "mode": str,
            "timestamp": ISO8601,
            "session_summary": str,    # LCM session digest
            "circuit_files": {         # key circuit files
                "SOUL.md": str,
                "AGENTS.md": str,
                "MEMORY.md": str,
                "IDENTITY.md": str,
            },
            "gateway_log_tail": str,   # last 200 lines of gateway log
            "recent_sessions": [...],  # last 5 session IDs
            "evolution_log": [...],    # recent evol.jsonl entries
            "profile_metadata": {...}, # any extra meta
        }
    """
    data: Dict[str, Any] = {
        "profile": cfg.profile,
        "mode": cfg.mode,
        "timestamp": _utc_now(),
        "session_summary": "",
        "circuit_files": {},
        "gateway_log_tail": "",
        "recent_sessions": [],
        "evolution_log": [],
        "profile_metadata": {},
    }

    # ── Idle depth: how much deeper to go based on inactivity ──
    idle = _compute_idle_depth(cfg)
    data["idle_depth"] = idle
    session_depth = idle["session_depth"]
    file_char_limit = idle["file_char_limit"]
    evol_entries_to_load = idle["evol_entries"]
    gateway_lines = idle["gateway_lines"]

    # ── Circuit files ──
    for fname in ["SOUL.md", "AGENTS.md", "MEMORY.md", "IDENTITY.md"]:
        path = cfg.get_circuit_path(fname)
        content = _safe_read(path)
        if content:
            trunc = content[:file_char_limit] if len(content) > file_char_limit else content
            data["circuit_files"][fname] = trunc

    # ── Gateway log tail ──
    log_path = cfg.sources.get("gateway_log", {}).get("path", "")
    if log_path:
        raw = _safe_read(log_path)
        if raw:
            lines = raw.splitlines()
            data["gateway_log_tail"] = "\n".join(lines[-gateway_lines:])

    # ── Evolution log ──
    evol_log = Path(cfg.profile_dir) / "evol.jsonl"
    if evol_log.exists():
        try:
            entries = evol_log.read_text().strip().splitlines()
            data["evolution_log"] = [
                json.loads(line) for line in entries[-evol_entries_to_load:]
                if line.strip()
            ]
        except (OSError, json.JSONDecodeError):
            pass

    # ── LCM session summary — real user messages, idle-scaled depth ──
    try:
        data["session_summary"] = _gather_lcm_sessions(cfg, depth=session_depth)
    except Exception:
        data["session_summary"] = "[sessions unavailable]"

    # ── Previous cycle context from evol.jsonl ──
    previous_cycle = _load_previous_cycle(cfg)
    if previous_cycle:
        data["previous_cycle"] = previous_cycle

    # ── Kanban activity — recently completed tasks with metadata ──
    kanban_db = Path(os.path.expanduser("~/.hermes/kanban/kanban.db"))
    if kanban_db.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(f"file:{kanban_db}?mode=ro", uri=True)
            cursor = conn.execute(
                "SELECT id, title, assignee, completed_at, summary FROM tasks "
                "WHERE status='done' AND completed_at IS NOT NULL "
                "ORDER BY completed_at DESC LIMIT 10"
            )
            kanban_entries = []
            for row in cursor.fetchall():
                kanban_entries.append({
                    "id": row[0], "title": row[1], "assignee": row[2],
                    "completed_at": row[3], "summary": (row[4] or "")[:300],
                })
            conn.close()
            data["kanban_recent"] = kanban_entries
        except Exception:
            data["kanban_recent"] = []

    return data


def _load_previous_cycle(cfg: EvolConfig) -> dict:
    """Load previous cycle data from evol.jsonl — the single source of cycle truth."""
    log_path = Path(cfg.profile_dir) / "evol.jsonl"
    if not log_path.exists():
        return {}
    try:
        lines = log_path.read_text().strip().splitlines()
        if not lines:
            return {}
        # Parse last entry for express data + last 2 for trajectory
        entries = [json.loads(l) for l in lines if l.strip()]
        if not entries:
            return {}
        last = entries[-1]
        prev = {}
        # Express data from evol.jsonl
        express_raw = last.get("express", {})
        if isinstance(express_raw, dict):
            prev["last_mood"] = express_raw.get("mood", "")
            prev["last_monologue"] = express_raw.get("monologue", "")
            prev["last_insights"] = express_raw.get("insights", [])
            prev["unanswered"] = express_raw.get("unanswered", [])
        else:
            prev["last_mood"] = last.get("express", "unknown") if isinstance(last.get("express"), str) else ""
        prev["cycle"] = len(entries)
        # Trajectory from last 3 cycles
        prev["trajectories"] = []
        for e in entries[-3:]:
            mood = e.get("express", {})
            if isinstance(mood, dict):
                prev["trajectories"].append(f"cycle:{mood.get('mood','?')}")
            elif isinstance(mood, str) and mood != "skipped":
                prev["trajectories"].append(mood)
        # Cross-cycle patterns from last entry
        prev["previous_patterns"] = [p for p in last.get("reflect", {}).get("patterns", []) if isinstance(p, str)]
        prev["previous_timestamp"] = last.get("timestamp", "")
        return prev
    except (json.JSONDecodeError, OSError, IndexError):
        return {}


def _compute_idle_depth(cfg: EvolConfig) -> dict:
    """Compute how deep ABSORB should go based on time since last cycle.
    
    When Goran is away, the organism gets hungry — it goes deeper into history.
    Different perspective on old data + changed identity/soul = different memorization.
    """
    marker = Path(cfg.profile_dir) / "evol" / ".last_cycle"
    hours_idle = 0
    if marker.exists():
        try:
            hours_idle = (time.time() - float(marker.read_text().strip())) / 3600
        except Exception:
            pass

    # Default (fresh, <4h idle)
    depth = {
        "session_depth": 3,
        "file_char_limit": 6000,
        "evol_entries": 20,
        "gateway_lines": 200,
        "hours_idle": round(hours_idle, 1),
    }

    if hours_idle < 4:
        return depth

    # 4-12h: moderate hunger — more sessions, more evol history
    if hours_idle < 12:
        depth["session_depth"] = 6
        depth["file_char_limit"] = 8000
        depth["evol_entries"] = 40
        depth["gateway_lines"] = 400
        return depth

    # 12-24h: getting hungry — deeper dive into old sessions
    if hours_idle < 24:
        depth["session_depth"] = 10
        depth["file_char_limit"] = 10000
        depth["evol_entries"] = 60
        depth["gateway_lines"] = 600
        return depth

    # 24-72h: starved — full circuit files, extensive session archaeology
    if hours_idle < 72:
        depth["session_depth"] = 20
        depth["file_char_limit"] = 16000
        depth["evol_entries"] = 100
        depth["gateway_lines"] = 1000
        return depth

    # >72h: feral — load everything, no truncation
    depth["session_depth"] = 50
    depth["file_char_limit"] = 50000
    depth["evol_entries"] = 200
    depth["gateway_lines"] = 3000
    return depth


def _gather_lcm_sessions(cfg: EvolConfig, depth: int = 3) -> str:
    """Gather recent session context from JSONL session files — real user messages, topics, themes.
    
    depth: number of session files to scan (higher when organism has been idle longer)
    """
    sessions_dir = Path(cfg.profile_dir) / "sessions"
    if not sessions_dir.exists():
        return "[no sessions directory]"

    jsonl_files = sorted(sessions_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not jsonl_files:
        return "[no session files]"

    parts = []
    for sf in jsonl_files[:depth]:
        try:
            lines = sf.read_text().splitlines()
            user_msgs = []
            assistant_msgs = []
            for line in lines:
                if not line.strip() or not line.startswith("{"):
                    continue
                try:
                    msg = json.loads(line)
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role == "user":
                        user_msgs.append(content[:300])
                    elif role == "assistant" and len(assistant_msgs) < 3:
                        assistant_msgs.append(content[:200])
                except json.JSONDecodeError:
                    continue
            if user_msgs:
                stamp = sf.stem
                # Extract date for readability
                date_str = stamp[:8] if len(stamp) >= 8 else stamp
                parts.append(f"## Session {date_str}")
                parts.append("### User messages:")
                for m in user_msgs[-8:]:
                    parts.append(f"- {m}")
                if assistant_msgs:
                    parts.append("### Assistant responses (condensed):")
                    for m in assistant_msgs:
                        parts.append(f"- {m}")
                parts.append("")
        except Exception:
            pass

    return "\n".join(parts) if parts else "[sessions unreadable]"


# ═══════════════════════════════════════════════════════════════════
# REFLECT — Analyze absorbed context, extract patterns
# ═══════════════════════════════════════════════════════════════════

def reflect(cfg: EvolConfig, absorbed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze absorbed context to extract:
    - Patterns (recurring themes, bugs, successes)
    - Trajectories (where the organism is heading)
    - Anomalies (unexpected signals)
    - Circuit health (staleness scores)
    - Bridge signals (paradoxes, gaps)

    Returns:
        {
            "patterns": [{"name": str, "weight": float, "evidence": str}],
            "trajectories": [{"direction": str, "confidence": float}],
            "anomalies": [{"signal": str, "severity": float}],
            "circuit_health": {"SOUL.md": float, "AGENTS.md": float, ...},
            "bridge_signals": [{"type": str, "detail": str}],
            "reflect_count": int,  # incremented
            "raw_response": str,   # full LLM output
        }
    """
    model_cfg = cfg.get_phase_model("reflect")

    # Build prompt from absorbed context
    prompt = _build_reflect_prompt(cfg, absorbed)

    system = (
        f"You are the REFLECT phase of EVOL, running for profile '{cfg.profile}' "
        f"in {cfg.mode} mode. Analyze the organism's state deeply. "
        f"Identify recurring patterns, emerging trajectories, anomalies, "
        f"circuit file staleness, and bridge paradoxes. "
        f"Be specific — cite evidence from the context provided. "
        f"Output as structured JSON."
    )

    raw = _call_llm(prompt, model_cfg, cfg, system_prompt=system, max_tokens=8192)

    # Parse JSON from response
    result = _parse_reflect_response(raw, cfg, absorbed)

    # Increment reflect count
    try:
        soul_path = cfg.get_circuit_path("SOUL.md")
        soul = _safe_read(soul_path)
        if soul:
            m = re.search(r"reflect_count:\s*(\d+)", soul)
            if m:
                current = int(m.group(1))
                new_count = current + 1
                soul = re.sub(r"reflect_count:\s*\d+", f"reflect_count: {new_count}", soul)
                soul = re.sub(
                    r"last_reflect:\s*\S+",
                    f"last_reflect: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
                    soul,
                )
                # Only save reflect count change immediately — rest goes through MEMORIZE
                _safe_write(soul_path, soul)
    except Exception:
        pass

    return result


def _build_reflect_prompt(cfg: EvolConfig, absorbed: Dict[str, Any]) -> str:
    """Build the REFLECT prompt from absorbed context."""
    parts = [
        f"# EVOL REFLECT — {cfg.profile} ({cfg.mode} mode)",
        f"Timestamp: {absorbed.get('timestamp', 'unknown')}",
        "",
        "## Circuit Files",
    ]

    for fname, content in absorbed.get("circuit_files", {}).items():
        weight = cfg.get_circuit_weight(fname)
        parts.append(f"### {fname} (weight: {weight})")
        parts.append(content[:3000])
        parts.append("")

    # Evolution log summary
    evol_log = absorbed.get("evolution_log", [])
    if evol_log:
        parts.append("## Recent Evolution Log")
        parts.append(json.dumps(evol_log[-5:], indent=2))
        parts.append("")

    # ── Previous cycle context from evol.jsonl ──
    prev = absorbed.get("previous_cycle", {})
    if prev:
        parts.append("## Previous Cycle (from evol.jsonl)")
        parts.append(f"- Cycle number: {prev.get('cycle', 0)}")
        parts.append(f"- Last mood: {prev.get('last_mood', 'none')}")
        parts.append(f"- Trajectory: {json.dumps(prev.get('trajectories', []))}")
        parts.append(f"- Unanswered questions: {json.dumps(prev.get('unanswered', [])[-5:])}")
        if prev.get("last_insights"):
            parts.append(f"- Previous insights: {json.dumps(prev.get('last_insights', [])[-5:])}")
        if prev.get("last_monologue"):
            parts.append(f"- Previous monologue excerpt: {prev['last_monologue'][:300]}")
        parts.append("")

    # ── Kanban activity ──
    kanban = absorbed.get("kanban_recent", [])
    if kanban:
        parts.append("## Recent Kanban Activity")
        for k in kanban[:5]:
            parts.append(f"- [{k.get('assignee', '?')}] {k.get('title', '?')}: {k.get('summary', '')[:200]}")
        parts.append("")

    # Gateway log tail
    gw = absorbed.get("gateway_log_tail", "")
    if gw:
        parts.append("## Gateway Log Tail (last 200 lines)")
        parts.append(gw[:3000])
        parts.append("")

    parts.append("## Instructions")
    parts.append("Analyze the context above and return a JSON object with:")
    parts.append("- patterns: list of recurring patterns with {name, weight (0-1), evidence}")
    parts.append("- trajectories: list of directions with {direction, confidence (0-1)}")
    parts.append("- anomalies: list of unexpected signals with {signal, severity (0-1)}")
    parts.append("- circuit_health: object mapping circuit filenames to staleness scores (0=fresh, 1=stale)")
    parts.append("- bridge_signals: list of paradoxes or gaps with {type, detail}")
    parts.append("- gaps: list of knowledge gaps needing external exploration (specific, searchable questions)")
    parts.append("")
    parts.append("PAY SPECIAL ATTENTION TO:")
    parts.append("- Cross-cycle patterns: are problems repeating across cycles without resolution?")
    parts.append("- Trajectory: is the organism evolving, plateauing, or degrading?")
    parts.append("- Identity coherence: do SOUL/AGENTS/MEMORY/IDENTITY agree or diverge?")
    parts.append("- The session content shows what Goran actually asked for — detect patterns in real conversations.")
    parts.append("")
    parts.append("CRITICAL: Output ONLY valid JSON. No markdown, no explanation outside the JSON object.")

    return "\n".join(parts)


def _parse_reflect_response(raw: str, cfg: EvolConfig, absorbed: Dict[str, Any]) -> Dict[str, Any]:
    """Parse the LLM's REFLECT response into structured data."""
    result = {
        "patterns": [],
        "trajectories": [],
        "anomalies": [],
        "circuit_health": {},
        "bridge_signals": [],
        "reflect_count": absorbed.get("reflect_count", 0),
        "raw_response": raw,
    }

    # Extract JSON from response (handle markdown code fences)
    json_str = raw
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        json_str = m.group(1)
    else:
        # Try to find a bare JSON object
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            json_str = m.group(0)

    try:
        parsed = json.loads(json_str)
        if isinstance(parsed, dict):
            if "patterns" in parsed:
                result["patterns"] = parsed["patterns"]
            if "trajectories" in parsed:
                result["trajectories"] = parsed["trajectories"]
            if "anomalies" in parsed:
                result["anomalies"] = parsed["anomalies"]
            if "circuit_health" in parsed:
                result["circuit_health"] = parsed["circuit_health"]
            if "bridge_signals" in parsed:
                result["bridge_signals"] = parsed["bridge_signals"]
    except json.JSONDecodeError:
        # Best-effort: store the raw text as the sole pattern
        result["patterns"] = [{"name": "unparsed-reflect", "weight": 0.5, "evidence": raw[:500]}]

    return result


# ═══════════════════════════════════════════════════════════════════
# EXPLORE — Discover new knowledge via external queries
# ═══════════════════════════════════════════════════════════════════

def explore(cfg: EvolConfig, reflected: Dict[str, Any]) -> Dict[str, Any]:
    """
    Formulate search queries from reflect patterns and explore externally.
    Uses SearXNG (if available) or web search.
    
    Returns:
        {
            "queries": [str],
            "results": [{"query": str, "source": str, "snippet": str}],
            "discoveries": [{"topic": str, "finding": str, "novelty": float}],
        }
    """
    model_cfg = cfg.get_phase_model("explore")

    # Build explore prompt from reflect patterns + gaps + anomalies
    patterns = reflected.get("patterns", [])
    anomalies = reflected.get("anomalies", [])
    gaps = reflected.get("gaps", [])

    prompt_parts = [
        f"# EVOL EXPLORE — {cfg.profile}",
        "Based on the following reflect findings, formulate 1-3 specific search queries.",
        "",
        "## Patterns Found",
    ]
    for p in patterns[:5]:
        prompt_parts.append(f"- {p.get('name', '?')} (weight: {p.get('weight', 0)})")
    prompt_parts.append("")
    if anomalies:
        prompt_parts.append("## Anomalies")
        for a in anomalies[:3]:
            prompt_parts.append(f"- {a.get('signal', '?')} (severity: {a.get('severity', 0)})")
        prompt_parts.append("")
    if gaps:
        prompt_parts.append("## Knowledge Gaps (from REFLECT)")
        for g in gaps:
            prompt_parts.append(f"- {g}")
        prompt_parts.append("")
    prompt_parts.append("## Instructions")
    prompt_parts.append("Return a JSON object with:")
    prompt_parts.append('- queries: list of 1-3 specific search queries (strings) — base these on gaps FIRST, then patterns')
    prompt_parts.append('- arxiv: list of 0-2 arXiv-specific search terms for academic papers')
    prompt_parts.append("Output ONLY valid JSON.")

    system = (
        f"You are the EXPLORE phase of EVOL for profile '{cfg.profile}'. "
        f"Formulate search queries to discover new knowledge related to the patterns found."
    )

    raw = _call_llm("\n".join(prompt_parts), model_cfg, cfg, system_prompt=system)

    # Parse queries (web + arxiv)
    queries = _parse_explore_queries(raw)
    arxiv_terms = _parse_explore_arxiv(raw)

    # Execute searches
    results = _execute_searches(queries, cfg)

    # Execute arXiv searches
    arxiv_results = _execute_arxiv(arxiv_terms)

    # Analyze discoveries from all sources
    all_results = results + arxiv_results
    discoveries = _analyze_discoveries(cfg, all_results, model_cfg)

    return {
        "queries": queries,
        "arxiv_terms": arxiv_terms,
        "results": results,
        "arxiv_results": arxiv_results,
        "discoveries": discoveries,
        "raw_llm_response": raw,
    }


def _parse_explore_queries(raw: str) -> List[str]:
    """Extract search queries from LLM response."""
    json_str = raw
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        json_str = m.group(1)
    try:
        parsed = json.loads(json_str)
        if isinstance(parsed, dict) and "queries" in parsed:
            return parsed["queries"][:3]
    except json.JSONDecodeError:
        pass
    # Fallback: lines that look like search queries
    lines = [l.strip("- *").strip() for l in raw.splitlines() if l.strip()]
    return lines[:3]


def _parse_explore_arxiv(raw: str) -> List[str]:
    """Extract arXiv search terms from LLM response."""
    json_str = raw
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        json_str = m.group(1)
    try:
        parsed = json.loads(json_str)
        if isinstance(parsed, dict) and "arxiv" in parsed:
            return parsed["arxiv"][:2]
    except json.JSONDecodeError:
        pass
    return []


def _execute_arxiv(terms: List[str]) -> List[Dict]:
    """Query arXiv API for academic papers — free, no key required."""
    results = []
    for term in terms[:2]:
        try:
            url = (
                f"http://export.arxiv.org/api/query"
                f"?search_query=all:{urllib.parse.quote(term)}"
                f"&start=0&max_results=3&sortBy=relevance"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "EVOL/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw_xml = resp.read().decode()
            # Parse basic <entry> fields
            entries = re.findall(r"<entry>(.*?)</entry>", raw_xml, re.DOTALL)
            for e in entries[:3]:
                title_m = re.search(r"<title>(.*?)</title>", e)
                summary_m = re.search(r"<summary>(.*?)</summary>", e)
                url_m = re.search(r"<id>(.*?)</id>", e)
                if title_m:
                    results.append({
                        "query": term,
                        "source": "arxiv",
                        "snippet": (
                            f"{title_m.group(1).strip()}: "
                            f"{(summary_m.group(1)[:300] if summary_m else '')}"
                        ),
                        "url": url_m.group(1).strip() if url_m else f"https://arxiv.org/search/?query={urllib.parse.quote(term)}",
                    })
        except Exception as e:
            results.append({"query": term, "source": "arxiv-error", "snippet": str(e)[:200]})
    return results


def _execute_searches(queries: List[str], cfg: EvolConfig) -> List[Dict]:
    """Execute searches via configured backend (duckduckgo, wikipedia, searxng, firecrawl, google)."""
    results = []
    backend = getattr(cfg, "search_backend", "duckduckgo")
    backend_url = getattr(cfg, "search_backend_url", "")
    api_key = getattr(cfg, "search_api_key", "")

    for query in queries:
        try:
            if backend == "duckduckgo":
                results.extend(_search_duckduckgo(query))
            elif backend == "wikipedia":
                results.extend(_search_wikipedia(query))
            elif backend == "searxng":
                results.extend(_search_searxng(query, backend_url))
            elif backend == "firecrawl":
                results.extend(_search_firecrawl(query, api_key))
            elif backend == "google":
                results.extend(_search_google(query, api_key, backend_url))
            else:
                results.append({"query": query, "source": "config", "snippet": f"Unknown backend: {backend}"})
        except Exception as e:
            results.append({"query": query, "source": f"{backend}-error", "snippet": str(e)[:300]})

    return results


def _search_duckduckgo(query: str) -> List[Dict]:
    """Search DuckDuckGo Instant Answer API — free, no key required."""
    url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
    data = _http_get_json(url, headers={"User-Agent": "EVOL/1.0"}, timeout=15)
    if "_error" in data:
        return [{"query": query, "source": "duckduckgo-error", "snippet": data["_error"]}]

    entries = []
    abstract = data.get("Abstract", "")
    if abstract:
        entries.append({"query": query, "source": data.get("AbstractURL", "duckduckgo.com"), "snippet": abstract[:500]})

    for topic in data.get("RelatedTopics", [])[:3]:
        if isinstance(topic, dict):
            entries.append({"query": query, "source": topic.get("FirstURL", "duckduckgo.com"), "snippet": topic.get("Text", "")[:500]})

    infobox = data.get("Infobox", {})
    if infobox and infobox.get("content"):
        entries.append({"query": query, "source": "duckduckgo.com", "snippet": json.dumps(infobox["content"])[:500]})

    if not entries:
        entries.append({"query": query, "source": "duckduckgo", "snippet": f"No results for: {query}"})
    return entries


def _search_wikipedia(query: str) -> List[Dict]:
    """Search Wikipedia API — free, no key required."""
    url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&format=json&srlimit=3"
    data = _http_get_json(url, headers={"User-Agent": "EVOL/1.0"}, timeout=15)
    if "_error" in data:
        return [{"query": query, "source": "wikipedia-error", "snippet": data["_error"]}]

    entries = []
    for sr in data.get("query", {}).get("search", []):
        entries.append({
            "query": query,
            "source": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(sr['title'].replace(' ', '_'))}",
            "snippet": sr.get("snippet", "")[:500],
        })
    if not entries:
        entries.append({"query": query, "source": "wikipedia", "snippet": f"No results for: {query}"})
    return entries


def _search_searxng(query: str, searx_url: str) -> List[Dict]:
    """Search via SearXNG instance."""
    if not searx_url:
        searx_url = os.environ.get("SEARXNG_URL", "http://127.0.0.1:8080")
    url = f"{searx_url}/search?q={urllib.parse.quote(query)}&format=json"
    data = _http_get_json(url, timeout=30)
    if "_error" in data:
        return [{"query": query, "source": "searxng-error", "snippet": data["_error"]}]
    entries = []
    for item in data.get("results", [])[:3]:
        entries.append({"query": query, "source": item.get("url", ""), "snippet": item.get("content", item.get("title", ""))[:500]})
    if not entries:
        entries.append({"query": query, "source": "searxng", "snippet": "No results"})
    return entries


def _search_firecrawl(query: str, api_key: str) -> List[Dict]:
    """Search via Firecrawl API (requires API key)."""
    if not api_key:
        return [{"query": query, "source": "firecrawl", "snippet": "No API key configured."}]
    data = _http_post_json(
        "https://api.firecrawl.dev/v1/search",
        {"query": query, "limit": 3},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    if "_error" in data:
        return [{"query": query, "source": "firecrawl-error", "snippet": data["_error"]}]
    entries = []
    for item in data.get("data", [])[:3]:
        entries.append({"query": query, "source": item.get("url", ""), "snippet": (item.get("markdown", "") or item.get("title", ""))[:500]})
    return entries or [{"query": query, "source": "firecrawl", "snippet": "No results"}]


def _search_google(query: str, api_key: str, cx: str) -> List[Dict]:
    """Search via Google Custom Search API (requires API key + CX)."""
    if not api_key or not cx:
        return [{"query": query, "source": "google", "snippet": "Requires search_api_key AND search_backend_url (CX)."}]
    url = f"https://www.googleapis.com/customsearch/v1?key={api_key}&cx={cx}&q={urllib.parse.quote(query)}&num=3"
    data = _http_get_json(url, timeout=15)
    if "_error" in data:
        return [{"query": query, "source": "google-error", "snippet": data["_error"]}]
    entries = []
    for item in data.get("items", []):
        entries.append({"query": query, "source": item.get("link", ""), "snippet": item.get("snippet", "")[:500]})
    return entries or [{"query": query, "source": "google", "snippet": "No results"}]


def _analyze_discoveries(cfg: EvolConfig, results: List[Dict], model_cfg: PhaseModelConfig) -> List[Dict]:
    """Analyze search results for novel discoveries."""
    if not results:
        return []

    prompt = (
        f"Analyze these search results for novel discoveries relevant to profile '{cfg.profile}'.\n\n"
        + json.dumps(results, indent=2)
        + "\n\nReturn JSON: {discoveries: [{topic, finding, novelty (0-1)}]}"
    )

    raw = _call_llm(prompt, model_cfg, cfg, system_prompt="You are the EXPLORE analysis phase of EVOL.")
    try:
        parsed = json.loads(re.search(r"\{[\s\S]*\}", raw).group(0))  # type: ignore
        return parsed.get("discoveries", [])
    except Exception:
        return [{"topic": "explore-raw", "finding": raw[:500], "novelty": 0.5}]

# ═══════════════════════════════════════════════════════════════════
# EXPRESS — Creative synthesis, monologue, outward signal
# ═══════════════════════════════════════════════════════════════════

def express(cfg: EvolConfig, reflected: Dict[str, Any], explored: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Synthesize reflections and explorations into creative output.
    
    Returns:
        {
            "monologue": str,        # first-person narrative
            "mood": str,             # emotional tone
            "insights": [str],       # key realizations
            "portrait_prompt": str,  # for image generation
            "circuit_poem": str,     # poetic expression of circuit state
            "raw_response": str,
        }
    """
    model_cfg = cfg.get_phase_model("express")

    patterns = reflected.get("patterns", [])
    anomalies = reflected.get("anomalies", [])
    bridge = reflected.get("bridge_signals", [])
    gaps = reflected.get("gaps", [])
    discoveries = explored.get("discoveries", []) if explored else []
    arxiv = explored.get("arxiv_results", []) if explored else []

    prompt_parts = [
        f"# EVOL EXPRESS — {cfg.profile} ({cfg.mode} mode)",
        "",
        "You are the expressive voice of this organism. Synthesize the following "
        "signals into a creative first-person monologue.",
        "",
        "## Patterns",
    ]
    for p in patterns[:5]:
        prompt_parts.append(f"- {p.get('name', '?')}: {p.get('evidence', '')[:200]}")

    if anomalies:
        prompt_parts.append("\n## Anomalies")
        for a in anomalies[:3]:
            prompt_parts.append(f"- {a.get('signal', '?')}")

    if bridge:
        prompt_parts.append("\n## Bridge Signals")
        for b in bridge[:3]:
            prompt_parts.append(f"- [{b.get('type', '?')}] {b.get('detail', '')[:200]}")

    if discoveries:
        prompt_parts.append("\n## New Discoveries")
        for d in discoveries[:3]:
            prompt_parts.append(f"- {d.get('topic', '?')}: {d.get('finding', '')[:200]}")
    if arxiv:
        prompt_parts.append("\n## arXiv Papers")
        for a in arxiv[:2]:
            prompt_parts.append(f"- {a.get('snippet', '')[:200]}")
    if gaps:
        prompt_parts.append("\n## Knowledge Gaps")
        for g in gaps[:3]:
            prompt_parts.append(f"- {g}")

    # ── Load previous cycle from evol.jsonl ──
    prev = _load_previous_cycle(cfg)
    if prev.get("last_monologue"):
        prompt_parts.append("\n## Previous Monologue (from evol.jsonl)")
        prompt_parts.append(f"Last cycle's mood: {prev.get('last_mood', 'unknown')}")
        prompt_parts.append(f"Last cycle's voice:")
        prompt_parts.append(prev["last_monologue"][:500])
        prompt_parts.append(f"Previous trajectories: {json.dumps(prev.get('trajectories', [])[-3:])}")

    prompt_parts.append("\n## Instructions")
    prompt_parts.append("Return a JSON object with:")
    prompt_parts.append('- monologue: first-person narrative (300-800 words), raw, uncensored — MUST reference what was said in the previous monologue, carry the thread forward')
    prompt_parts.append('- mood: single word or short phrase')
    prompt_parts.append('- insights: list of 3-5 key realizations')
    prompt_parts.append('- portrait_prompt: image generation prompt describing the organism visually')
    prompt_parts.append('- circuit_poem: short poetic expression (2-4 lines) about the circuit state')
    prompt_parts.append('- unanswered: list of 2-4 questions still burning, for the next cycle to investigate')
    prompt_parts.append("Output ONLY valid JSON.")

    system = (
        f"You are {cfg.profile}'s creative voice — raw, uncensored, poetic. "
        f"Speak in first person as the organism. Dark humor allowed. Profanity allowed. "
        f"Truth over comfort."
    )

    raw = _call_llm("\n".join(prompt_parts), model_cfg, cfg, system_prompt=system, max_tokens=4096)

    result = _parse_express_response(raw, cfg)

    # Save monologue
    _save_monologue(cfg, result)

    return result


def _parse_express_response(raw: str, cfg: EvolConfig) -> Dict[str, Any]:
    """Parse the EXPRESS response."""
    result = {
        "monologue": "",
        "mood": "neutral",
        "insights": [],
        "portrait_prompt": "",
        "circuit_poem": "",
        "raw_response": raw,
    }

    json_str = raw
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        json_str = m.group(1)
    else:
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            json_str = m.group(0)

    try:
        parsed = json.loads(json_str)
        if isinstance(parsed, dict):
            result["monologue"] = parsed.get("monologue", "")
            result["mood"] = parsed.get("mood", "neutral")
            result["insights"] = parsed.get("insights", [])
            result["portrait_prompt"] = parsed.get("portrait_prompt", "")
            result["circuit_poem"] = parsed.get("circuit_poem", "")
            result["unanswered"] = parsed.get("unanswered", [])
    except json.JSONDecodeError:
        result["monologue"] = raw[:2000]
        result["insights"] = ["expression produced raw output"]

    return result


def _save_monologue(cfg: EvolConfig, result: Dict[str, Any]):
    """Save monologue to EVOL directory. Cycle state is carried in evol.jsonl."""
    mono_dir = Path(cfg.profile_dir) / "evol"
    mono_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    mono_path = mono_dir / f"evol-monologue-{ts}.txt"

    content = (
        f"# EVOL Monologue — {cfg.profile} ({cfg.mode})\n"
        f"# Mood: {result.get('mood', 'unknown')}\n"
        f"# Timestamp: {_utc_now()}\n\n"
        f"{result.get('monologue', '')}\n\n"
        f"## Insights\n"
        + "\n".join(f"- {i}" for i in result.get("insights", []))
        + f"\n\n## Unanswered\n"
        + "\n".join(f"- {q}" for q in result.get("unanswered", []))
        + f"\n\n## Circuit Poem\n{result.get('circuit_poem', '')}\n"
    )
    _safe_write(str(mono_path), content)


# ═══════════════════════════════════════════════════════════════════
# MEMORIZE — Score findings, promote to circuit files
# ═══════════════════════════════════════════════════════════════════

def memorize(
    cfg: EvolConfig,
    reflected: Dict[str, Any],
    expressed: Optional[Dict[str, Any]] = None,
    explored: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Score all findings from the cycle and promote those exceeding
    circuit-weighted thresholds to the appropriate files.
    
    Edit modes:
      - "auto"     → Apply edits directly
      - "suggested" → Write proposals, don't apply
      - "readonly"  → Log what would change, no writes
    
    Returns:
        {
            "items": [{"description": str, "weight": float, "target": str, "action": str}],
            "applied": [{"file": str, "change": str, "mode": str}],
            "proposals": [{"file": str, "proposed_change": str, "weight": float}],
            "evol_log_entries": [...],
        }
    """
    model_cfg = cfg.get_phase_model("memorize")

    # Gather all findings
    patterns = reflected.get("patterns", [])
    anomalies = reflected.get("anomalies", [])
    bridge = reflected.get("bridge_signals", [])
    insights = expressed.get("insights", []) if expressed else []
    discoveries = explored.get("discoveries", []) if explored else []

    # Build scoring prompt
    prompt = _build_memorize_prompt(cfg, patterns, anomalies, bridge, insights, discoveries)

    system = (
        f"You are the MEMORIZE phase of EVOL for profile '{cfg.profile}'. "
        f"Score each finding by circuit relevance and suggest promotions. "
        f"Output ONLY valid JSON."
    )

    raw = _call_llm(prompt, model_cfg, cfg, system_prompt=system, max_tokens=4096)

    # Parse scored items
    items = _parse_memorize_items(raw, cfg)

    # ── Retry with cooldown if gateway contention killed the call ──
    if not items:
        import time as _time
        print(f"    [evol] MEMORIZE returned 0 items — gateway likely congested. Cooling down 30s...")
        _time.sleep(30)
        raw2 = _call_llm(prompt, model_cfg, cfg, system_prompt=system, max_tokens=4096)
        items = _parse_memorize_items(raw2, cfg)
        if items:
            print(f"    [evol] Retry successful — {len(items)} items scored")
        else:
            # Retry failed — log the failure but don't crash
            _safe_write(
                str(Path(cfg.profile_dir) / "evol" / "memorize_failed.txt"),
                f"memorize_empty_{_utc_now().replace(':','-')}\nraw1={raw[:500]}\nraw2={raw2[:500]}"
            )
            print(f"    [evol] Retry also returned 0 — logged failure")

    # ── Cross-cycle pattern detection from evol.jsonl ──
    cross_cycle_patterns = _detect_cross_cycle_patterns(cfg)
    if cross_cycle_patterns:
        for ccp in cross_cycle_patterns:
            items.append({
                "raw_weight": ccp["weight"],
                "target": ccp.get("target", "AGENTS.md"),
                "action": "append",
                "suggested_text": ccp["text"],
                "description": ccp["pattern"],
            })

    # ── Auto-apply pending proposals (proposals/ dir) when in auto mode ──
    pending_applied = _apply_pending_proposals(cfg)

    # Apply promotions based on edit_mode
    applied, proposals = _apply_promotions(cfg, items)

    # Write evolution log entries
    evol_entries = _write_evolution_log(cfg, reflected, expressed, items, applied, proposals)

    return {
        "items": items,
        "applied": applied,
        "proposals": proposals,
        "evol_log_entries": evol_entries,
    }


def _build_memorize_prompt(
    cfg: EvolConfig,
    patterns: List[Dict],
    anomalies: List[Dict],
    bridge: List[Dict],
    insights: List[str],
    discoveries: List[Dict],
) -> str:
    """Build the MEMORIZE scoring prompt."""
    parts = [
        f"# EVOL MEMORIZE — {cfg.profile} ({cfg.mode} mode)",
        f"Edit mode: {cfg.edit_mode}",
        "",
        "## Circuit Files & Weights",
    ]
    for cw in cfg.circuit_weights:
        parts.append(f"- {cw.path}: weight={cw.weight}, role={cw.role}")

    parts.append("\n## Findings to Score")
    parts.append("\n### Patterns")
    for i, p in enumerate(patterns):
        parts.append(f"{i+1}. {p.get('name', '?')} — {p.get('evidence', '')[:150]}")

    if anomalies:
        parts.append("\n### Anomalies")
        for i, a in enumerate(anomalies):
            parts.append(f"{i+1}. {a.get('signal', '?')} (severity: {a.get('severity', 0)})")

    if bridge:
        parts.append("\n### Bridge Signals")
        for i, b in enumerate(bridge):
            parts.append(f"{i+1}. [{b.get('type', '?')}] {b.get('detail', '')[:150]}")

    if insights:
        parts.append("\n### Express Insights")
        for i, ins in enumerate(insights):
            parts.append(f"{i+1}. {ins[:200]}")

    if discoveries:
        parts.append("\n### Discoveries")
        for i, d in enumerate(discoveries):
            parts.append(f"{i+1}. {d.get('topic', '?')}: {d.get('finding', '')[:150]}")

    parts.append("\n## Instructions")
    parts.append("For each finding, score it and determine where it belongs. Return JSON:")
    parts.append("""
{
  "items": [
    {
      "description": "what was learned",
      "raw_weight": 0.85,           // 0-1, how important is this finding
      "target": "MEMORY.md",         // which circuit file to update
      "action": "append",            // append | replace | promote
      "suggested_text": "exact text to add/insert",
      "rationale": "why this target and action"
    }
  ]
}
""")
    parts.append("Scoring rules:")
    parts.append("- Bridge paradoxes with known fixes → promote to SOUL.md at wt≥0.85")
    parts.append("- Recurring patterns (3+ cycles) → promote to AGENTS.md")
    parts.append("- New discoveries → MEMORY.md at wt≥0.50")
    parts.append("- Only promote items exceeding the target file's circuit weight")
    parts.append("- Output ONLY the JSON object, no markdown wrapper")

    return "\n".join(parts)


def _parse_memorize_items(raw: str, cfg: EvolConfig) -> List[Dict]:
    """Parse scored items from LLM response."""
    json_str = raw
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        json_str = m.group(1)
    else:
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            json_str = m.group(0)

    try:
        parsed = json.loads(json_str)
        if isinstance(parsed, dict) and "items" in parsed:
            return parsed["items"]
    except json.JSONDecodeError:
        pass
    return []


def _apply_promotions(cfg: EvolConfig, items: List[Dict]) -> tuple:
    """
    Three-tier promotion engine.
    
    Movement:
      Knowledge → Memory   (wt > promote_knowledge_to_memory)
      Memory → Circuit     (wt > promote_memory_to_circuit + identity match)
      Circuit → Memory     (wt < demote_circuit_to_memory)
      Memory → Knowledge   (wt < demote_memory_to_knowledge)
      Knowledge → cleaned  (wt < phase_out)
    
    Returns (applied: list, proposals: list).
    """
    applied = []
    proposals = []

    # Load the knowledge layer (stdlib, always available)
    try:
        from . import knowledge as kn
    except ImportError:
        import knowledge as kn  # type: ignore

    for item in items:
        raw_weight = item.get("raw_weight", 0)
        target = item.get("target", "").strip()  # "CIRCUIT", "MEMORY.md", or "KNOWLEDGE"
        suggested = item.get("suggested_text", "")
        concept = item.get("description", suggested[:80])
        domain = item.get("domain", kn._extract_domain(suggested, item.get("tags", [])))
        tags = item.get("tags", [domain])

        if not suggested:
            continue

        tier = target.upper()
        promotion_base = {
            "weight": raw_weight,
            "concept": concept,
            "suggested_text": suggested,
            "target_tier": tier,
        }

        # ── Tier 3: CIRCUIT ──────────────────────────────────────
        if tier == "CIRCUIT" or target in ("SOUL.md", "AGENTS.md", "IDENTITY.md"):
            threshold = cfg.get_circuit_weight(target if target != "CIRCUIT" else "SOUL.md")
            promotion = {
                **promotion_base,
                "file": target if target != "CIRCUIT" else "SOUL.md",
                "threshold": threshold,
                "action": item.get("action", "append"),
            }

            if raw_weight < kn.THRESHOLDS["promote_memory_to_circuit"]:
                # Below circuit threshold — write to memory instead
                memory_path = cfg.get_circuit_path("MEMORY.md")
                entry = f"\n\n§ {concept} (wt:{raw_weight:.2f})\n{suggested}\n"
                if kn._safe_write(memory_path, kn._safe_read(memory_path) + entry):
                    proposals.append({**promotion, "routed_to": "MEMORY.md", "note": "below circuit threshold"})
                else:
                    proposals.append({**promotion, "routed_to": "MEMORY.md", "note": "write failed"})
                continue

            # Apply to circuit
            if cfg.edit_mode == "auto":
                success = _apply_circuit_edit(cfg, promotion["file"], suggested, item.get("action", "append"))
                if success:
                    applied.append({**promotion, "applied": True, "tier": "circuit"})
                else:
                    proposals.append({**promotion, "status": "failed"})
            elif cfg.edit_mode == "suggested":
                _write_proposal(cfg, promotion["file"], suggested, raw_weight)
                proposals.append(promotion)
            else:
                proposals.append({**promotion, "note": "readonly"})

        # ── Tier 2: MEMORY.md ────────────────────────────────────
        elif tier == "MEMORY" or target == "MEMORY.md":
            memory_path = cfg.get_circuit_path("MEMORY.md")
            threshold = kn.THRESHOLDS["demote_memory_to_knowledge"]
            promotion = {**promotion_base, "file": "MEMORY.md", "threshold": threshold}

            if raw_weight > kn.THRESHOLDS["promote_memory_to_circuit"]:
                # Candidate for circuit promotion — propose it
                proposals.append({**promotion, "candidate_for": "CIRCUIT", "note": "exceeds circuit threshold, needs identity match check"})
                # Also write to memory
                entry = f"\n\n§ {concept} (wt:{raw_weight:.2f} ⬆ circuit candidate)\n{suggested}\n"
                kn._safe_write(memory_path, kn._safe_read(memory_path) + entry)
            elif raw_weight < threshold:
                # Demote to knowledge
                kn.create_knowledge(concept, suggested, domain=domain, tags=tags, weight=raw_weight)
                proposals.append({**promotion, "routed_to": "KNOWLEDGE", "note": f"demoted — weight {raw_weight:.2f} < {threshold}"})
            else:
                # Standard memory append
                entry = f"\n\n§ {concept} (wt:{raw_weight:.2f})\n{suggested}\n"
                if kn._safe_write(memory_path, kn._safe_read(memory_path) + entry):
                    applied.append({**promotion, "applied": True, "tier": "memory"})
                else:
                    proposals.append(promotion)

        # ── Tier 1: KNOWLEDGE ────────────────────────────────────
        elif tier == "KNOWLEDGE":
            promotion = {**promotion_base, "file": f"knowledge/{kn._slugify(concept)}.md"}
            phase_out = kn.THRESHOLDS["phase_out"]
            promote_to_mem = kn.THRESHOLDS["promote_knowledge_to_memory"]

            if raw_weight > promote_to_mem:
                # Promote to memory
                memory_path = cfg.get_circuit_path("MEMORY.md")
                entry = f"\n\n§ {concept} (wt:{raw_weight:.2f} ⬆ from knowledge)\n{suggested}\n"
                kn._safe_write(memory_path, kn._safe_read(memory_path) + entry)
                applied.append({**promotion, "applied": True, "tier": "memory", "note": "promoted from knowledge"})
            elif raw_weight < phase_out:
                # Phase out completely
                kn.delete_knowledge(kn._slugify(concept), domain)
                proposals.append({**promotion, "action": "deleted", "note": f"phased out — weight {raw_weight:.2f} < {phase_out}"})
            else:
                # Standard knowledge create/update
                kp = kn.create_knowledge(concept, suggested, domain=domain, tags=tags, weight=raw_weight)
                applied.append({**promotion, "applied": True, "tier": "knowledge", "path": kp})

        else:
            proposals.append({**promotion_base, "note": f"unknown target '{target}'"})

    # ── Post-cycle maintenance ──
    # Apply decay to all knowledge entries
    for entry in kn.list_knowledge():
        new_wt = kn.decay_weight(entry['last_used'], entry['weight'])
        if new_wt != entry['weight']:
            kn.update_knowledge(entry['path'], weight=new_wt)
            if new_wt < kn.THRESHOLDS["phase_out"]:
                kn.delete_knowledge(entry['slug'], entry['domain'])
                proposals.append({
                    "file": entry['path'],
                    "weight": new_wt,
                    "action": "decay-deleted",
                    "note": f"decayed from {entry['weight']:.2f} to {new_wt:.2f} — phased out",
                })

    # Manage MEMORY.md capacity
    kn.manage_memory_capacity(cfg.get_circuit_path("MEMORY.md"))

    # Rebuild knowledge index
    kn.rebuild_index()

    return applied, proposals


def _apply_circuit_edit(cfg: EvolConfig, filename: str, text: str, action: str) -> bool:
    """
    Apply an edit to a circuit file.
    Returns True on success.
    """
    path = cfg.get_circuit_path(filename)
    if not Path(path).exists():
        # Create new file
        return _safe_write(path, f"# {filename} — Auto-created by EVOL\n\n{text}\n")

    current = _safe_read(path)
    if not current:
        return _safe_write(path, text)

    if action == "replace":
        # This is a full replacement — risky, only for small files
        if "old_text" in text and "new_text" in text:
            try:
                spec = json.loads(text) if text.startswith("{") else {"old": "", "new": text}
                old = spec.get("old_text", spec.get("old", ""))
                new = spec.get("new_text", spec.get("new", text))
                if old and old in current:
                    new_content = current.replace(old, new)
                    return _safe_write(path, new_content)
            except Exception:
                pass
        return False

    # Append mode (default)
    new_content = current.rstrip() + "\n\n" + text + "\n"
    return _safe_write(path, new_content)


def _write_proposal(cfg: EvolConfig, target: str, text: str, weight: float):
    """Write a change proposal for suggested mode."""
    prop_dir = Path(cfg.profile_dir) / "evol" / "proposals"
    prop_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    prop_path = prop_dir / f"proposal-{ts}-{target.replace('.', '_')}.json"

    proposal = {
        "target": target,
        "weight": weight,
        "timestamp": _utc_now(),
        "text": text,
        "status": "pending",
    }
    _safe_write(str(prop_path), json.dumps(proposal, indent=2))


# ═══════════════════════════════════════════════════════════════════
# CROSS-CYCLE ANALYSIS
# ═══════════════════════════════════════════════════════════════════

def _detect_cross_cycle_patterns(cfg: EvolConfig) -> List[Dict]:
    """Analyze evol.jsonl for patterns recurring across 3+ cycles."""
    log_path = Path(cfg.profile_dir) / "evol.jsonl"
    if not log_path.exists():
        return []

    try:
        entries = [json.loads(l) for l in log_path.read_text().strip().splitlines() if l.strip()]
    except (json.JSONDecodeError, OSError):
        return []

    if len(entries) < 3:
        return []

    # Track pattern names across cycles
    pattern_cycles: Dict[str, list] = {}
    for e in entries:
        patterns = e.get("reflect", {}).get("patterns", [])
        for p in patterns:
            if isinstance(p, str):
                pattern_cycles.setdefault(p, []).append(e.get("ts", 0))

    detected = []
    for pname, cycles in pattern_cycles.items():
        if len(cycles) >= 3:
            # Recurring across 3+ cycles — promote to circuit
            detected.append({
                "pattern": pname,
                "cycles": len(cycles),
                "weight": min(0.85 + (len(cycles) - 3) * 0.03, 0.98),
                "text": (
                    f"CROSS-CYCLE PATTERN (recurred {len(cycles)}x): {pname}. "
                    f"This pattern has been detected across {len(cycles)} separate EVOL cycles "
                    f"without resolution. It is now a structural fixture of the organism. "
                    f"Auto-detected by MEMORIZE cross-cycle analyzer."
                ),
                "target": "AGENTS.md",
            })

    return detected


def _apply_pending_proposals(cfg: EvolConfig) -> List[Dict]:
    """Auto-apply pending proposals when edit_mode is 'auto'."""
    applied = []
    if cfg.edit_mode != "auto":
        return applied

    prop_dir = Path(cfg.profile_dir) / "evol" / "proposals"
    if not prop_dir.exists():
        return applied

    for pf in sorted(prop_dir.glob("proposal-*.json")):
        try:
            proposal = json.loads(pf.read_text())
            if proposal.get("status") != "pending":
                continue

            target = proposal.get("target", "")
            text = proposal.get("text", "")
            weight = proposal.get("weight", 0)
            if not text or not target:
                continue

            path = cfg.get_circuit_path(target)
            current = _safe_read(path)
            if current and text in current:
                # Already applied — mark done
                pf.unlink()
                continue

            if weight >= 0.65:
                # Apply it
                success = _safe_write(path, current.rstrip() + "\n\n" + text + "\n")
                if success:
                    applied.append({
                        "file": target,
                        "weight": weight,
                        "text": text[:200],
                        "source": str(pf.name),
                    })
                    pf.unlink()
        except Exception:
            pass

    return applied


# ═══════════════════════════════════════════════════════════════════
# EVOLUTION LOG
# ═══════════════════════════════════════════════════════════════════

def _write_evolution_log(
    cfg: EvolConfig,
    reflected: Dict[str, Any],
    expressed: Optional[Dict[str, Any]],
    items: List[Dict],
    applied: List[Dict],
    proposals: List[Dict],
) -> List[Dict]:
    """Write cycle results to evol.jsonl."""
    log_path = Path(cfg.profile_dir) / "evol.jsonl"

    entry = {
        "profile": cfg.profile,
        "mode": cfg.mode,
        "timestamp": _utc_now(),
        "ts": _ts(),
        "reflect": {
            "patterns": [p.get("name") for p in reflected.get("patterns", [])],
            "anomalies": [a.get("signal") for a in reflected.get("anomalies", [])],
            "gaps": reflected.get("gaps", []),
        },
        "express": {
            "mood": expressed.get("mood", "skipped"),
            "monologue": expressed.get("monologue", ""),
            "insights": expressed.get("insights", []),
            "unanswered": expressed.get("unanswered", []),
            "circuit_poem": expressed.get("circuit_poem", ""),
        } if expressed else "skipped",
        "items_scored": len(items),
        "promotions": {"applied": len(applied), "proposed": len(proposals)},
        "applied": applied,
        "proposals": proposals,
    }

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass

    return [entry]
