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
# VERBOSITY & DRY-RUN HELPERS
# ═══════════════════════════════════════════════════════════════════

def _vlog(cfg, level: int, msg: str):
    """Print if config verbosity >= level. 0=silent, 1=summary, 2=detailed, 3=full."""
    verbosity = getattr(cfg, 'verbosity', 1)
    if verbosity >= level:
        prefix = "[DRY-RUN] " if getattr(cfg, 'dry_run', False) else ""
        print(f"{prefix}{msg}")

def _dry_write(path: str, content: str, cfg) -> bool:
    """Write to a file unless in dry-run mode. Logs what would be written."""
    if getattr(cfg, 'dry_run', False):
        _vlog(cfg, 2, f"  [dry] Would write {len(content)} bytes to {Path(path).name}")
        return True
    return _safe_write(path, content)

def _dry_append(path: str, content: str, cfg) -> bool:
    """Append to a file unless in dry-run mode."""
    if getattr(cfg, 'dry_run', False):
        _vlog(cfg, 2, f"  [dry] Would append {len(content)} bytes to {Path(path).name}")
        return True
    current = _safe_read(path)
    return _safe_write(path, current + content)

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

def _safe_write(path: str, content: str) -> bool:
    """Write a file, create parents, silent on failure. Returns True on success."""
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return True
    except OSError:
        return False


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
    # Resolve provider/model from profile's Hermes config.yaml
    # Every profile has provider/model configured. Default to ollama-cloud.
    provider = phase_config.provider or cfg._hermes_provider or "ollama-cloud"
    model = phase_config.model or cfg._hermes_model or "deepseek-v4-pro"
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
        # Strip GLM-style thinking tokens (MiniMax, Venice GLM, etc.)
        # Pattern variants: "\nresponse\n", "\n response\n", "\nresponse", "\nresponse"
        if content:
            for boundary in ["\nresponse\n", "\nresponse\n", "\n response\n", "\nresponse"]:
                if boundary in content:
                    content = content[content.rindex(boundary) + len(boundary):].strip()
                    break
            else:
                # Last resort: "thinking\n" prefix
                if content.strip().startswith("thinking") and "\n" in content:
                    content = content.split("\n", 1)[1].strip()
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
    _vlog(cfg, 1, "━━━ EVOL ABSORB ━━━")
    _vlog(cfg, 1, f"  Profile: {cfg.profile} | Mode: {cfg.mode} | Dry-run: {cfg.dry_run}")
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

    _vlog(cfg, 1, f"  Absorbed: {len(data['evolution_log'])} evol entries, {len(data['kanban_recent'])} kanban tasks, {len(data['circuit_files'])} circuit files")
    _vlog(cfg, 2, f"  Sessions: {data['session_summary'][:100]}..." if len(data.get('session_summary', '')) > 100 else f"  Sessions: {data.get('session_summary', '[none]')}")
    
    # ── Verbosity 3: full detail dump ──
    _vlog(cfg, 3, f"  [v3] Circuit files loaded:")
    for fname, content in data.get('circuit_files', {}).items():
        _vlog(cfg, 3, f"    {fname}: {len(content)} chars")
    _vlog(cfg, 3, f"  [v3] Session summary:\n{data.get('session_summary', '[none]')[:2000]}")
    _vlog(cfg, 3, f"  [v3] Idle depth: {json.dumps(data.get('idle_depth', {}))}")
    _vlog(cfg, 3, f"  [v3] Kanban recent: {json.dumps(data.get('kanban_recent', [])[:3])}")
    _vlog(cfg, 3, f"  [v3] Previous cycle: {json.dumps(data.get('previous_cycle', {}).get('cycle', 'none'))}")
    
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
    _vlog(cfg, 1, "━━━ EVOL REFLECT ━━━")
    _vlog(cfg, 1, f"  Context: {len(absorbed.get('circuit_files', {}))} circuit files, {len(absorbed.get('evolution_log', []))} evol entries")
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

    _vlog(cfg, 1, f"  Reflect found: {len(result['patterns'])} patterns, {len(result['anomalies'])} anomalies, {len(result.get('bridge_signals', []))} bridge signals")
    _vlog(cfg, 2, f"  Patterns: {[p.get('name','?') for p in result['patterns']]}")
    
    # ── Verbosity 3: full detail dump ──
    _vlog(cfg, 3, "  [v3] Full REFLECT output:")
    for p in result.get('patterns', [])[:5]:
        _vlog(cfg, 3, f"    pattern: {p.get('name','?')} (wt={p.get('weight',0):.2f})")
        _vlog(cfg, 3, f"      evidence: {p.get('evidence','')[:200]}")
    for a in result.get('anomalies', [])[:3]:
        _vlog(cfg, 3, f"    anomaly: {a.get('signal','?')} (severity={a.get('severity',0):.2f})")
    for b in result.get('bridge_signals', [])[:3]:
        _vlog(cfg, 3, f"    bridge: [{b.get('type','?')}] {b.get('detail','')[:150]}")
    for c in result.get('circuit_health', {}).items():
        _vlog(cfg, 3, f"    circuit: {c[0]}={c[1]}")
    _vlog(cfg, 3, f"  [v3] Raw LLM response ({len(result.get('raw_response',''))} chars):\n{result.get('raw_response','')[:1000]}")
    
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

def explore(cfg: EvolConfig, reflected: Dict[str, Any], query_limit: int = 3) -> Dict[str, Any]:
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
    _vlog(cfg, 1, "━━━ EVOL EXPLORE ━━━")
    model_cfg = cfg.get_phase_model("explore")

    # Build explore prompt from reflect patterns + gaps + anomalies
    patterns = reflected.get("patterns", [])
    anomalies = reflected.get("anomalies", [])
    gaps = reflected.get("gaps", [])

    prompt_parts = [
        f"# EVOL EXPLORE — {cfg.profile}",
        "Based on the reflect findings below, generate SHORT KEYWORD PHRASES for web search engines.",
        "CRITICAL: Write 2-5 word keyword phrases, NOT full questions. Search engines match keywords, not interrogatives.",
        '  GOOD: "multi-agent orchestration pattern"',
        '  GOOD: "recursive self-improvement agents"',
        '  BAD: "What are the critical gaps in understanding agent coordination?"',
        '  BAD: "How do multi-agent systems handle recursive patterns of self-organization?"',
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
    prompt_parts.append('- queries: list of 1-3 keyword search phrases (2-5 words each, NOT questions) — derive from gaps FIRST, then patterns')
    prompt_parts.append('- arxiv: list of 0-2 arXiv-specific search terms (keyword style, 2-4 words)')
    prompt_parts.append("Output ONLY valid JSON.")

    system = (
        f"You are the EXPLORE phase of EVOL for profile '{cfg.profile}'. "
        f"Convert reflect findings into short keyword search phrases. "
        f"NEVER produce full-sentence questions. Always 2-5 word keyword phrases."
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

    _vlog(cfg, 1, f"  Explore: {len(queries)} queries, {len(all_results)} results, {len(discoveries)} discoveries")
    _vlog(cfg, 2, f"  Queries: {queries}")
    
    # ── Verbosity 3: full detail dump ──
    _vlog(cfg, 3, f"  [v3] Search results ({len(all_results)}):")
    for r in all_results[:5]:
        _vlog(cfg, 3, f"    [{r.get('source','?')}] {r.get('snippet','')[:200]}")
    _vlog(cfg, 3, f"  [v3] Discoveries ({len(discoveries)}):")
    for d in discoveries[:5]:
        _vlog(cfg, 3, f"    {d.get('topic','?')} (novelty={d.get('novelty',0):.2f}): {d.get('finding','')[:150]}")

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
    """Execute searches via ALL configured backends. Configure via evol.json:
    { "search_backends": [{"name":"wikipedia"}, {"name":"searxng","url":"http://..."}, {"name":"arxiv"}] }
    Falls back to single search_backend for backward compatibility."""
    results = []

    # Build backend list from config
    backends = getattr(cfg, "search_backends", None) or []
    if not backends:
        # Backward compat — single backend
        backends = [{
            "name": getattr(cfg, "search_backend", "wikipedia"),
            "url": getattr(cfg, "search_backend_url", ""),
            "key": getattr(cfg, "search_api_key", ""),
        }]

    for query in queries:
        for be in backends:
            name = be.get("name", "wikipedia")
            url = be.get("url", "")
            key = be.get("key", "")
            try:
                if name == "duckduckgo":
                    results.extend(_search_duckduckgo(query))
                elif name == "wikipedia":
                    results.extend(_search_wikipedia(query))
                elif name == "searxng":
                    results.extend(_search_searxng(query, url))
                elif name == "firecrawl":
                    results.extend(_search_firecrawl(query, key))
                elif name == "google":
                    results.extend(_search_google(query, key, url))
                elif name == "arxiv":
                    results.extend(_execute_arxiv([query]))
                elif name == "reddit":
                    results.extend(_search_reddit(query))
                else:
                    results.append({"query": query, "source": name, "snippet": f"Unknown backend: {name}"})
            except Exception as e:
                results.append({"query": query, "source": f"{name}-error", "snippet": str(e)[:300]})

    return results


def _search_duckduckgo(query: str) -> List[Dict]:
    """Search DuckDuckGo HTML endpoint — free, no key required, returns real web results."""
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return [{"query": query, "source": "duckduckgo-error", "snippet": str(e)}]

    # Parse result snippets from HTML
    entries = []
    import re
    # Extract result blocks: <a class="result__a" href="URL">TITLE</a> ... <a class="result__snippet">SNIPPET</a>
    blocks = re.split(r'<a class="result__a"', html)[1:]  # skip before first result
    for block in blocks[:5]:
        url_match = re.search(r'href="([^"]+)"', block)
        title_match = re.search(r'>([^<]+)</a>', block)
        snippet_match = re.search(r'class="result__snippet">(.+?)</a>', block, re.DOTALL)
        if url_match and snippet_match:
            title = title_match.group(1).strip() if title_match else query
            snippet = re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip()
            entries.append({
                "query": query,
                "source": url_match.group(1),
                "snippet": f"{title}: {snippet[:500]}"
            })

    if not entries:
        entries.append({"query": query, "source": "duckduckgo", "snippet": f"No web results for: {query}"})
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
    url = f"https://www.googleapis.com/customsearch/v1?key=***&cx={cx}&q={urllib.parse.quote(query)}&num=3"
    data = _http_get_json(url, timeout=15)
    if "_error" in data:
        return [{"query": query, "source": "google-error", "snippet": data["_error"]}]
    entries = []
    for item in data.get("items", []):
        entries.append({"query": query, "source": item.get("link", ""), "snippet": item.get("snippet", "")[:500]})
    return entries or [{"query": query, "source": "google", "snippet": "No results"}]


def _search_reddit(query: str) -> List[Dict]:
    """Search Reddit via public JSON API — free, no key required."""
    url = f"https://www.reddit.com/search.json?q={urllib.parse.quote(query)}&limit=3&sort=relevance"
    data = _http_get_json(url, headers={"User-Agent": "EVOL/1.0"}, timeout=15)
    if "_error" in data:
        return [{"query": query, "source": "reddit-error", "snippet": data["_error"]}]
    entries = []
    for child in data.get("data", {}).get("children", [])[:3]:
        d = child.get("data", {})
        entries.append({
            "query": query,
            "source": f"https://reddit.com{d.get('permalink', '')}",
            "snippet": f"r/{d.get('subreddit', '')}: {d.get('title', '')} {d.get('selftext', '')}",
        })
    return entries or [{"query": query, "source": "reddit", "snippet": "No results"}]


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

def express(cfg: EvolConfig, reflected: Dict[str, Any], explored: Optional[Dict[str, Any]] = None, style: str = "creative") -> Dict[str, Any]:
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
    _vlog(cfg, 1, "━━━ EVOL EXPRESS ━━━")
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

    # Save monologue (respects dry-run)
    _save_monologue(cfg, result)

    _vlog(cfg, 1, f"  Express: mood={result.get('mood','?')}, {len(result.get('insights',[]))} insights")
    _vlog(cfg, 2, f"  Monologue preview: {result.get('monologue','')[:100]}...")
    
    # ── Verbosity 3: full detail dump ──
    _vlog(cfg, 3, f"  [v3] Full EXPRESS output:")
    _vlog(cfg, 3, f"    monologue: {result.get('monologue','')[:1500]}")
    _vlog(cfg, 3, f"    mood: {result.get('mood','?')}")
    _vlog(cfg, 3, f"    insights: {json.dumps(result.get('insights',[]))}")
    _vlog(cfg, 3, f"    unanswered: {json.dumps(result.get('unanswered',[]))}")
    _vlog(cfg, 3, f"    portrait_prompt: {result.get('portrait_prompt','')[:200]}")
    _vlog(cfg, 3, f"    circuit_poem: {result.get('circuit_poem','')}")

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
    # Save monologue to EVOL directory. Cycle state is carried in evol.jsonl.
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
    _dry_write(str(mono_path), content, cfg)


# ═══════════════════════════════════════════════════════════════════
# MEMORIZE — Score findings, promote to circuit files
# ═══════════════════════════════════════════════════════════════════

def memorize(
    cfg: EvolConfig,
    reflected: Dict[str, Any],
    expressed: Optional[Dict[str, Any]] = None,
    explored: Optional[Dict[str, Any]] = None,
    scope: str = "full",
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
    _vlog(cfg, 1, "━━━ EVOL MEMORIZE ━━━")
    _vlog(cfg, 1, f"  Mode: approval={cfg.approval_mode} | edit={cfg.edit_mode} | dry={cfg.dry_run}")
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
        # Skip cooldown in dry-run mode — cross-cycle detector already has items
        if getattr(cfg, 'dry_run', False):
            cross_cycle_patterns = _detect_cross_cycle_patterns(cfg)
            if cross_cycle_patterns:
                _vlog(cfg, 2, "    MEMORIZE LLM returned 0 items, using cross-cycle detector (dry-run skip cooldown)")
        else:
            print(f"    [evol] MEMORIZE returned 0 items — gateway likely congested. Cooling down 30s...")
            _time.sleep(30)
            raw2 = _call_llm(prompt, model_cfg, cfg, system_prompt=system, max_tokens=4096)
            items = _parse_memorize_items(raw2, cfg)
            if items:
                print(f"    [evol] Retry successful — {len(items)} items scored")
            else:
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

    # ── TIER 2 MEMORY: Promotion/demotion to external memory graph ──
    tier2_result = {"promoted": [], "demoted": [], "skipped": 0, "errors": 0, "backend": "none"}
    try:
        try:
            from . import tier2_memory as t2
        except (ImportError, ValueError):
            import tier2_memory as t2

        backend = t2.create_tier2_backend({
            "tier2_backend": getattr(cfg, "tier2_backend", "graphiti"),
            "tier2_config": getattr(cfg, "tier2_config", {}),
        })
        _vlog(cfg, 1, f"    TIER2 backend: {backend.name()} — health: {backend.health()}")
        
        # Convert EVOL scored items to tier2 facts
        tier2_facts = []
        for it in items:
            tier2_facts.append({
                "description": it.get("description", ""),
                "weight": it.get("raw_weight", 0),
                "concept": it.get("description", it.get("suggested_text", ""))[:80],
                "source": f"EVOL cycle {cfg.profile}",
                "tags": it.get("tags", ["evol"]),
                "suggested_text": it.get("suggested_text", ""),
                "contradicts": it.get("contradicts", []),
            })
        
        tier2_result = t2.run_promotion_demotion_cycle(
            tier2_facts, backend,
            promote_threshold=0.65,
            demote_threshold=0.35,
            access_threshold=5,
        )
        _vlog(cfg, 1, f"    Tier2: ↑{len(tier2_result['promoted'])} ↓{len(tier2_result['demoted'])} —{tier2_result['skipped']} !{tier2_result['errors']}")
    except ImportError as e:
        print(f"    [evol] TIER2: module not available ({e})")
    except Exception as e:
        print(f"    [evol] TIER2 error: {e}")

    # Apply promotions based on edit_mode + approval_mode
    applied, proposals = _apply_promotions(cfg, items)

    # Write evolution log entries
    evol_entries = _write_evolution_log(cfg, reflected, expressed, items, applied, proposals, tier2_result)

    return {
        "items": items,
        "applied": applied,
        "proposals": proposals,
        "evol_log_entries": evol_entries,
        "tier2": tier2_result,
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

    parts.append("\n## Valid Target Files (choose one per item)")
    parts.append("- SOUL.md     — identity-level changes: role soul, fundamental behaviors, character shifts (≥0.85)")
    parts.append("- AGENTS.md   — new gates, procedural rules, anti-patterns (≥0.75)")
    parts.append("- MEMORY.md   — working knowledge, gotchas, techniques, domain facts (≥0.50)")
    parts.append("- KNOWLEDGE   — low-weight trivia, one-off facts (<0.50)")
    parts.append("")
    parts.append("## Demotion Rules (STRICT — never skip steps)")
    parts.append("- CIRCUIT → MEMORY.md first (never directly to KNOWLEDGE)")
    parts.append("- MEMORY.md → KNOWLEDGE only after being in MEMORY.md")
    parts.append("- KNOWLEDGE → phase out (delete) when weight < 0.15")
    parts.append("")
    parts.append("\n## Instructions")
    # MiniMax: use compact instructions to save token budget for thinking tokens
    if cfg.get_phase_model("memorize").provider == "minimax":
        parts.append(
            'Score each finding. Return EXACT JSON, no markdown:\n'
            '{"items":[{"description":"name","raw_weight":0.9,"target":"AGENTS.md",'
            '"action":"append","suggested_text":"| G-NAME | When | Do |","rationale":"why"}]}\n'
            'RULES: SOUL.md if >=0.85, AGENTS.md if >=0.75, MEMORY.md if >=0.50. Output ONLY JSON.'
        )
    else:
        parts.append("For each finding, score it and determine where it belongs. Return JSON:")
        parts.append("""
{
  "items": [
    {
      "description": "what was learned",
      "raw_weight": 0.85,
      "target": "SOUL.md",
      "action": "append",
      "suggested_text": "| 2026-05-19 | PATTERN-NAME (wt:0.85) -- explanation | EVOL session MEMORIZE |",
      "rationale": "why this target and weight"
    }
  ]
}
""")
        parts.append("Scoring rules:")
        parts.append("- Identity-defining insights about the role's SOUL -> SOUL.md at wt>=0.85")
        parts.append("- Recurring mistakes or new procedural rules -> AGENTS.md at wt>=0.75")
        parts.append("- Practical techniques, gotchas, domain knowledge -> MEMORY.md at wt>=0.50")
        parts.append("- Output ONLY the JSON object, no markdown wrapper")

    return "\n".join(parts)


def _parse_memorize_items(raw: str, cfg: EvolConfig) -> List[Dict]:
    """Parse scored items from LLM response.
    Handles GLM-style thinking tokens, inline markdown, and malformed JSON."""
    json_str = raw
    
    # Strip thinking tokens (belt-and-suspenders)
    if "\nresponse" in json_str:
        json_str = json_str[json_str.rindex("\nresponse") + len("\nresponse"):].strip()
    elif json_str.strip().startswith("thinking") and "\n" in json_str:
        json_str = json_str.split("\n", 1)[1].strip()
    
    # Try 1: Code-fenced JSON block
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", json_str)
    if m:
        try:
            parsed = json.loads(m.group(1))
            if isinstance(parsed, dict) and "items" in parsed:
                return parsed["items"]
        except json.JSONDecodeError:
            pass
    
    # Try 2: Raw JSON object with items key
    m = re.search(r"\{[\s\S]*\"items\"[\s\S]*\}", json_str)
    if m:
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, dict) and "items" in parsed:
                return parsed["items"]
        except json.JSONDecodeError:
            pass
    
    # Try 3: Array of items (some models skip the wrapper)
    m = re.search(r"\[\s*\{[\s\S]*\"description\"[\s\S]*\}\]", json_str)
    if m:
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, list) and len(parsed) > 0 and "description" in parsed[0]:
                return parsed
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
                success = _apply_circuit_edit(
                    cfg, promotion["file"], suggested,
                    item.get("action", "append"),
                    concept=concept, weight=raw_weight
                )
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


def _format_circuit_entry(filename: str, concept: str, text: str, weight: float) -> str:
    """
    Format a circuit file append in standard CIRCUIT format (circuit-file-editing skill).
    SOUL.md / IDENTITY.md / AGENTS.md → Evolution Log table row
    MEMORY.md → § marker + table row in Core Patterns
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = concept.strip().replace("\n", " ")[:80]

    if filename in ("SOUL.md", "IDENTITY.md", "AGENTS.md"):
        # Standard Evolution Log table row
        return f"| {today} | {slug} (wt:{weight:.2f}) | {text.strip()[:200]} |"

    elif filename == "MEMORY.md":
        return f"\n§ {slug} (wt:{weight:.2f})\n{text.strip()}\n"

    else:
        # Generic: § marker
        return f"\n§ {slug} (wt:{weight:.2f})\n{text.strip()}\n"


def _apply_circuit_edit(cfg: EvolConfig, filename: str, text: str, action: str,
                        concept: str = "", weight: float = 0.5) -> bool:
    """
    Apply an edit to a circuit file respecting CIRCUIT format standards.
    - SOUL/AGENTS/IDENTITY: appends to ## Evolution Log table
    - MEMORY.md: appends § marker entries
    - Preserves YAML frontmatter on new file creation
    Returns True on success.
    """
    path = cfg.get_circuit_path(filename)
    formatted = _format_circuit_entry(filename, concept or "EVOL finding", text, weight)

    if not Path(path).exists():
        # Create with proper YAML frontmatter
        frontmatter = f"---\nrole: {filename.replace('.md', '')}\nlast_reflect: {_utc_now()[:10]}\nreflect_count: 0\n---\n\n"
        return _safe_write(path, frontmatter + f"# {filename} — Auto-created by EVOL\n\n## Evolution Log\n\n{formatted}\n")

    current = _safe_read(path)
    if not current:
        return _safe_write(path, formatted)

    if action == "replace":
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

    # Append to the correct section
    if filename in ("SOUL.md", "IDENTITY.md", "AGENTS.md"):
        # Find ## Evolution Log section, append table row
        evo_section = "## Evolution Log"
        if evo_section in current:
            # Insert before next ## section or at end
            sections = current.split("\n## ")
            for i, s in enumerate(sections):
                if s.startswith("Evolution Log"):
                    # Append to this section (before next section if exists)
                    parts = s.split("\n\n", 1)
                    if len(parts) > 1 and "|" in parts[1].split("\n")[0]:
                        # Already has a table — append row
                        sections[i] = parts[0] + "\n\n" + parts[1].rstrip() + "\n" + formatted
                    else:
                        # No table yet — add table header + row
                        table_header = "| Date | Promotion | Source |\n|------|-----------|--------|"
                        sections[i] = parts[0] + "\n\n" + table_header + "\n" + formatted
                    break
            new_content = "\n## ".join(sections)
        else:
            # No Evolution Log section — append one at end
            table_header = "\n## Evolution Log\n\n| Date | Promotion | Source |\n|------|-----------|--------|"
            new_content = current.rstrip() + table_header + "\n" + formatted + "\n"
    else:
        # MEMORY.md or other — plain append
        new_content = current.rstrip() + formatted + "\n"

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
    tier2_result: Dict[str, Any] = None,
) -> List[Dict]:
    """Write cycle results to evol.jsonl with full visibility."""
    log_path = Path(cfg.profile_dir) / "evol.jsonl"

    if tier2_result is None:
        tier2_result = {"promoted": [], "demoted": [], "skipped": 0, "errors": 0}

    entry = {
        "profile": cfg.profile,
        "mode": cfg.mode,
        "timestamp": _utc_now(),
        "ts": _ts(),
        "approval_mode": getattr(cfg, "approval_mode", "suggested"),
        "reflect": {
            "patterns": [p.get("name") for p in reflected.get("patterns", [])],
            "anomalies": [a.get("signal") for a in reflected.get("anomalies", [])],
            "gaps": reflected.get("gaps", []),
        },
        "express": {
            "mood": expressed.get("mood", "skipped"),
            "insights": expressed.get("insights", []),
            "unanswered": expressed.get("unanswered", []),
        } if expressed else "skipped",
        "scored": {
            "total": len(items),
            "promoted_circuit": len([i for i in items if i.get("target") in ("SOUL.md", "AGENTS.md", "IDENTITY.md")]),
            "promoted_memory": len([i for i in items if i.get("target") == "MEMORY.md"]),
            "promoted_knowledge": len([i for i in items if i.get("target") == "KNOWLEDGE"]),
        },
        "tier2": {
            "backend": tier2_result.get("backend", "none"),
            "promoted": [{"concept": p["concept"], "weight": p["weight"]} for p in tier2_result.get("promoted", [])],
            "demoted": [{"uuid": d["uuid"], "reason": d["reason"]} for d in tier2_result.get("demoted", [])],
            "skipped": tier2_result.get("skipped", 0),
            "errors": tier2_result.get("errors", 0),
        },
        "circuit": {
            "applied": applied,
            "proposals": proposals,
        },
        "items": items,
    }

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass

    return [entry]
