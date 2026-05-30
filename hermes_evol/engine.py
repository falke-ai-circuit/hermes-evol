"""
EVOL Engine — Cycle Orchestrator.

Runs the 5-phase cycle: absorb → reflect → explore → express → memorize.
Supports profile mode (one profile's data) and global mode (all profiles aggregated).

Also handles:
  - Phase enable/disable toggles
  - Per-phase model configuration
  - Edit mode (auto/suggested/readonly)
  - Cooldown enforcement
  - Retry logic (max_retries_per_phase)

Entry point: run_cycle(profile="conductor")
"""

import time
import json
import os
import threading
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

log = logging.getLogger(__name__)

# Relative import for plugin context, absolute fallback for standalone testing
try:
    from .config import EvolConfig
    from .registry import absorb, reflect, explore, express, memorize
    from .registry import _utc_now
except ImportError:
    from config import EvolConfig
    from registry import absorb, reflect, explore, express, memorize
    from registry import _utc_now


def run_cycle(
    profile: Optional[str] = None,
    mode: Optional[str] = None,
    force: bool = False,
    skip_phases: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Run a complete EVOL cycle for a profile.

    Args:
        profile: Profile name (auto-detected if None)
        mode: "profile" or "global" (from config if None)
        force: Skip cooldown checks
        skip_phases: List of phase names to skip (e.g. ["explore", "express"])

    Returns:
        {
            "status": "ok" | "skipped" | "error",
            "profile": str,
            "mode": str,
            "phases": {
                "absorb": {...},
                "reflect": {...},
                "explore": {...},
                "express": {...},
                "memorize": {...},
            },
            "duration_seconds": float,
            "error": str if status == "error",
        }
    """
    t_start = time.time()
    skip = set(skip_phases or [])

    # ── Load config ──
    try:
        cfg = EvolConfig(profile=profile, mode=mode)
    except Exception as e:
        return {"status": "error", "profile": profile or "unknown", "error": f"Config load failed: {e}"}

    result: Dict[str, Any] = {
        "status": "ok",
        "profile": cfg.profile,
        "mode": cfg.mode,
        "phases": {},
        "duration_seconds": 0,
    }

    # ── Quick checks ──
    if not cfg.enabled:
        return {**result, "status": "skipped", "reason": "EVOL disabled"}

    if not force and not _should_run(cfg):
        return {**result, "status": "skipped", "reason": "cooldown"}

    # ═══════════════════════════════════════════════════════════
    # GATHER SIDE: absorb → reflect → explore
    # ═══════════════════════════════════════════════════════════

    # ── PHASE 1: ABSORB (profile: 1 call, global: absorb all profiles → merge) ──
    if "absorb" not in skip and cfg.is_phase_enabled("absorb"):
        try:
            if cfg.mode == "global":
                absorbed = _absorb_global(cfg)
            else:
                absorbed = _run_with_retry(absorb, cfg, phase_name="absorb")
            result["phases"]["absorb"] = {"status": "ok", "sources_count": len(absorbed.get("circuit_files", {})), "data": absorbed}
            _run_phase_post_hook(cfg, "absorb", absorbed, result)
        except Exception as e:
            result["phases"]["absorb"] = {"status": "error", "error": str(e)}
            return {**result, "status": "error", "error": f"absorb failed: {e}"}
    else:
        absorbed = {"profile": cfg.profile, "mode": cfg.mode, "circuit_files": {}, "session_summary": ""}
        result["phases"]["absorb"] = {"status": "skipped"}

    # ── PHASE 2: REFLECT ──
    if "reflect" not in skip and cfg.is_phase_enabled("reflect"):
        try:
            reflected = _run_with_retry(reflect, cfg, absorbed, phase_name="reflect")
            result["phases"]["reflect"] = {
                "status": "ok",
                "patterns": len(reflected.get("patterns", [])),
                "anomalies": len(reflected.get("anomalies", [])),
                "bridge_signals": len(reflected.get("bridge_signals", [])),
                "data": reflected,
            }
            _run_phase_post_hook(cfg, "reflect", reflected, result)
        except Exception as e:
            result["phases"]["reflect"] = {"status": "error", "error": str(e)}
            reflected = {"patterns": [], "anomalies": [], "bridge_signals": [], "circuit_health": {}}
    else:
        reflected = {"patterns": [], "anomalies": [], "bridge_signals": [], "circuit_health": {}}
        result["phases"]["reflect"] = {"status": "skipped"}

    # ── PHASE 3: EXPLORE ──
    if "explore" not in skip and cfg.is_phase_enabled("explore"):
        try:
            explored = _run_with_retry(explore, cfg, reflected, phase_name="explore")
            result["phases"]["explore"] = {
                "status": "ok",
                "queries": explored.get("queries", []),
                "discoveries": len(explored.get("discoveries", [])),
                "data": explored,
            }
            _run_phase_post_hook(cfg, "explore", explored, result)
        except Exception as e:
            result["phases"]["explore"] = {"status": "error", "error": str(e)}
            explored = {"queries": [], "results": [], "discoveries": []}
    else:
        explored = {"queries": [], "results": [], "discoveries": []}
        result["phases"]["explore"] = {"status": "skipped"}

    # ═══════════════════════════════════════════════════════════
    # OUTPUT SIDE: express → memorize
    # ═══════════════════════════════════════════════════════════

    # ── PHASE 4: EXPRESS ──
    if "express" not in skip and cfg.is_phase_enabled("express"):
        if not force and not _express_can_run(cfg):
            result["phases"]["express"] = {"status": "skipped", "reason": "cooldown"}
            expressed = None
        else:
            try:
                expressed = _run_with_retry(express, cfg, reflected, explored, phase_name="express")
                result["phases"]["express"] = {
                    "status": "ok",
                    "mood": expressed.get("mood", "unknown"),
                    "insights": len(expressed.get("insights", [])),
                    "data": expressed,
                }
                _touch_last_express(cfg)
                # Generic post-phase hook
                _run_phase_post_hook(cfg, "express", expressed, result)
            except Exception as e:
                result["phases"]["express"] = {"status": "error", "error": str(e)}
                expressed = None
    else:
        expressed = None
        result["phases"]["express"] = {"status": "skipped"}

    # ── PHASE 5: MEMORIZE ──
    if "memorize" not in skip and cfg.is_phase_enabled("memorize"):
        try:
            memorized = _run_with_retry(memorize, cfg, reflected, expressed, explored, phase_name="memorize")
            result["phases"]["memorize"] = {
                "status": "ok",
                "items_scored": len(memorized.get("items", [])),
                "applied": len(memorized.get("applied", [])),
                "proposed": len(memorized.get("proposals", [])),
                "data": memorized,
            }
            _run_phase_post_hook(cfg, "memorize", memorized, result)
        except Exception as e:
            result["phases"]["memorize"] = {"status": "error", "error": str(e)}
    else:
        result["phases"]["memorize"] = {"status": "skipped"}

    # ── Finalize ──
    _touch_last_cycle(cfg)
    result["duration_seconds"] = round(time.time() - t_start, 2)

    return result


def run_session_cycle(
    profile: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a single-shot EVOL cycle for session mode (subagent task-end).

    Designed for ephemeral agents: coder finishes a task, calls evol_task_end,
    runs absorb→reflect→express→explore→memorize immediately, then exits.

    Differences from persistent run_cycle:
      - No cooldown checks (single-shot trigger)
      - No heartbeat, no cascade counters, no idle depth
      - Absorb: latest session + role circuit files only + role evol.jsonl
      - Express: synthesis style (key insight articulated for explore)
      - Explore: limited queries (default 1), single backend
      - Memorize: role-scoped — writes to role MEMORY.md, skills, evol.jsonl
        NEVER touches conductor circuit (SOUL.md/AGENTS.md/IDENTITY.md)
    """
    t_start = time.time()

    try:
        cfg = EvolConfig(profile=profile)
    except Exception as e:
        return {"status": "error", "profile": profile or "unknown", "error": f"Config load failed: {e}"}

    result: Dict[str, Any] = {
        "status": "ok",
        "profile": cfg.profile,
        "mode": "session",
        "phases": {},
        "duration_seconds": 0,
    }

    if not cfg.enabled:
        return {**result, "status": "skipped", "reason": "EVOL disabled"}

    # ═══ PHASE 1: ABSORB (session-scoped) ═══
    if cfg.is_phase_enabled("absorb"):
        try:
            absorbed = _absorb_session(cfg, session_id)
            result["phases"]["absorb"] = {
                "status": "ok",
                "sources_count": len(absorbed.get("circuit_files", {})),
                "data": absorbed,
            }
        except Exception as e:
            result["phases"]["absorb"] = {"status": "error", "error": str(e)}
            return {**result, "status": "error", "error": f"absorb failed: {e}"}
    else:
        absorbed = {"profile": cfg.profile, "circuit_files": {}, "session_summary": ""}
        result["phases"]["absorb"] = {"status": "skipped"}

    # ═══ PHASE 2: REFLECT ═══
    if cfg.is_phase_enabled("reflect"):
        try:
            reflected = _run_with_retry(reflect, cfg, absorbed, phase_name="reflect")
            result["phases"]["reflect"] = {
                "status": "ok",
                "patterns": len(reflected.get("patterns", [])),
                "anomalies": len(reflected.get("anomalies", [])),
                "data": reflected,
            }
        except Exception as e:
            result["phases"]["reflect"] = {"status": "error", "error": str(e)}
            reflected = {"patterns": [], "anomalies": [], "bridge_signals": [], "circuit_health": {}}
    else:
        reflected = {"patterns": [], "anomalies": [], "bridge_signals": [], "circuit_health": {}}
        result["phases"]["reflect"] = {"status": "skipped"}

    # ═══ PHASE 3: EXPRESS (synthesis style) ═══
    expressed = None
    if cfg.is_phase_enabled("express"):
        try:
            expressed = _run_with_retry(express, cfg, reflected, None, phase_name="express",
                                        style=cfg.express_style)
            result["phases"]["express"] = {
                "status": "ok",
                "style": cfg.express_style,
                "insights": len(expressed.get("insights", [])),
                "data": expressed,
            }
        except Exception as e:
            result["phases"]["express"] = {"status": "error", "error": str(e)}

    # ═══ PHASE 4: EXPLORE (limited queries) ═══
    explored = {"queries": [], "results": [], "discoveries": []}
    if cfg.is_phase_enabled("explore"):
        try:
            explored = _run_with_retry(explore, cfg, reflected, phase_name="explore",
                                       query_limit=cfg.explore_query_limit)
            result["phases"]["explore"] = {
                "status": "ok",
                "queries": explored.get("queries", []),
                "discoveries": len(explored.get("discoveries", [])),
                "data": explored,
            }
        except Exception as e:
            result["phases"]["explore"] = {"status": "error", "error": str(e)}

    # ═══ PHASE 5: MEMORIZE (role-scoped) ═══
    if cfg.is_phase_enabled("memorize"):
        try:
            memorized = _run_with_retry(memorize, cfg, reflected, expressed, explored,
                                        phase_name="memorize", scope="role")
            result["phases"]["memorize"] = {
                "status": "ok",
                "applied": len(memorized.get("applied", [])),
                "proposed": len(memorized.get("proposals", [])),
                "data": memorized,
            }
        except Exception as e:
            result["phases"]["memorize"] = {"status": "error", "error": str(e)}
    else:
        result["phases"]["memorize"] = {"status": "skipped"}

    result["duration_seconds"] = round(time.time() - t_start, 2)
    return result


def _absorb_session(cfg: EvolConfig, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Session-mode absorb: latest session + role circuit files + role evol.jsonl.
    No idle depth. No gateway logs. No conductor circuit files."""
    data: Dict[str, Any] = {
        "profile": cfg.profile,
        "timestamp": _utc_now(),
        "session_summary": "",
        "circuit_files": {},
        "evolution_log": [],
        "session_id": session_id,
    }

    # Role circuit files — the profile's own SOUL.md, AGENTS.md, MEMORY.md
    for fname in ["SOUL.md", "AGENTS.md", "MEMORY.md"]:
        path = cfg.get_circuit_path(fname)
        content = _safe_read(path)
        if content:
            data["circuit_files"][fname] = content[:6000]

    # Latest session data
    sessions_dir = Path(cfg.profile_dir) / "sessions"
    if sessions_dir.exists():
        jsonl_files = sorted(sessions_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if jsonl_files:
            try:
                lines = jsonl_files[0].read_text().splitlines()
                msgs = []
                for line in lines[-200:]:  # last 200 messages
                    try:
                        msg = json.loads(line)
                        role = msg.get("role", "?")
                        content = msg.get("content", "")[:300]
                        if content:
                            msgs.append(f"[{role}] {content}")
                    except (json.JSONDecodeError, KeyError):
                        pass
                data["session_summary"] = "\n".join(msgs[-100:])  # cap at 100 messages
            except (OSError, IOError):
                data["session_summary"] = "[session data unavailable]"
    else:
        data["session_summary"] = "[no sessions directory]"

    # Role evol.jsonl
    evol_log = Path(cfg.profile_dir) / "evol.jsonl"
    if evol_log.exists():
        try:
            entries = [json.loads(l) for l in evol_log.read_text().splitlines()[-10:]]
            data["evolution_log"] = entries
        except (json.JSONDecodeError, OSError):
            pass

    return data


def _safe_read(path) -> str:
    """Read file content safely, return empty string on failure."""
    try:
        return Path(path).read_text()
    except (OSError, IOError):
        return ""


def _absorb_global(cfg: EvolConfig) -> Dict[str, Any]:
    """Absorb ALL profiles and merge into one combined context.
    Single LLM call per phase, not per profile. 5 calls total for a global cycle."""
    profiles = cfg.global_profiles or cfg._discover_profiles()
    combined: Dict[str, Any] = {
        "profile": "global",
        "mode": "global",
        "timestamp": _utc_now(),
        "circuit_files": {},
        "session_summary": "",
        "evolution_log": [],
        "gateway_log_tail": "",
        "profiles_absorbed": [],
    }
    for prof in profiles:
        try:
            pc = EvolConfig(profile=prof)
            pc.search_backend = cfg.search_backend  # inherit
            a = absorb(pc)
            for fn, content in a.get("circuit_files", {}).items():
                combined["circuit_files"][f"{prof}/{fn}"] = content
            if a.get("session_summary"):
                combined["session_summary"] += f"\n[{prof}] {a['session_summary'][:300]}"
            combined["evolution_log"].extend(a.get("evolution_log", [])[-5:])
            combined["profiles_absorbed"].append(prof)
        except Exception:
            pass
    return combined


# ═══════════════════════════════════════════════════════════════════
# PER-AGENT EVOL CYCLE — v2: event-driven, self-calibrating
# ═══════════════════════════════════════════════════════════════════

def run_per_agent_cycle(
    agent_profile: str,
    cfg: Optional[EvolConfig] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Run a complete per-agent EVOL cycle scoped to a single agent.

    Self-calibrating trigger (AgentZero-inspired):
      - >3 tool calls AND >2000 tokens → EVOL fires
      - Trivial sessions (single file check, "hello") don't trigger

    5-phase cycle: absorb_agent → reflect → explore → express → memorize_agent
    All phases scoped to the target agent. No cross-agent contamination.

    Args:
        agent_profile: Target agent (e.g. "coder")
        cfg: EvolConfig (auto-created if None)
        force: Skip threshold and cooldown checks

    Returns:
        Same shape as run_cycle() result dict
    """
    t_start = time.time()

    if cfg is None:
        try:
            cfg = EvolConfig(profile=agent_profile)
        except Exception as e:
            return {"status": "error", "profile": agent_profile, "error": f"Config load failed: {e}"}

    result: Dict[str, Any] = {
        "status": "ok",
        "profile": agent_profile,
        "mode": "per_agent",
        "phases": {},
        "duration_seconds": 0,
    }

    if not cfg.enabled:
        return {**result, "status": "skipped", "reason": "EVOL disabled"}

    # ── Threshold check (completion-count based, file-backed) ──
    if not force:
        try:
            from .stores import AgentSessionTracker
            tracker = AgentSessionTracker()
            min_completions = cfg.per_agent_min_completions
            cooldown_h = cfg.per_agent_cooldown_hours
            if not tracker.check_threshold(agent_profile, min_completions, cooldown_h):
                return {**result, "status": "skipped",
                        "reason": f"threshold not met (need {min_completions} completions)"}
        except ImportError:
            from stores import AgentSessionTracker
            tracker = AgentSessionTracker()
            if not tracker.check_threshold(agent_profile,
                                           cfg.per_agent_min_completions,
                                           cfg.per_agent_cooldown_hours):
                return {**result, "status": "skipped",
                        "reason": "threshold not met"}

    # ═══ PHASE 1: ABSORB (agent-scoped) ═══
    if cfg.is_phase_enabled("absorb"):
        try:
            from .registry import absorb_agent
            absorbed = absorb_agent(cfg, agent_profile)
        except ImportError:
            from registry import absorb_agent
            absorbed = absorb_agent(cfg, agent_profile)
        result["phases"]["absorb"] = {
            "status": "ok",
            "sources_count": len(absorbed.get("circuit_files", {})),
            "data": absorbed,
        }
    else:
        absorbed = {"profile": agent_profile, "mode": "per_agent", "circuit_files": {}, "session_summary": ""}
        result["phases"]["absorb"] = {"status": "skipped"}

    # ═══ PHASE 2: REFLECT ═══
    if cfg.is_phase_enabled("reflect"):
        try:
            reflected = _run_with_retry(reflect, cfg, absorbed, phase_name="reflect")
            result["phases"]["reflect"] = {
                "status": "ok",
                "patterns": len(reflected.get("patterns", [])),
                "anomalies": len(reflected.get("anomalies", [])),
                "data": reflected,
            }
        except Exception as e:
            result["phases"]["reflect"] = {"status": "error", "error": str(e)}
            reflected = {"patterns": [], "anomalies": [], "bridge_signals": [], "circuit_health": {}}
    else:
        reflected = {"patterns": [], "anomalies": [], "bridge_signals": [], "circuit_health": {}}
        result["phases"]["reflect"] = {"status": "skipped"}

    # ═══ PHASE 3: EXPLORE ═══
    if cfg.is_phase_enabled("explore"):
        try:
            explored = _run_with_retry(explore, cfg, reflected, phase_name="explore")
            result["phases"]["explore"] = {
                "status": "ok",
                "queries": explored.get("queries", []),
                "discoveries": len(explored.get("discoveries", [])),
                "data": explored,
            }
        except Exception as e:
            result["phases"]["explore"] = {"status": "error", "error": str(e)}
            explored = {"queries": [], "results": [], "discoveries": []}
    else:
        explored = {"queries": [], "results": [], "discoveries": []}
        result["phases"]["explore"] = {"status": "skipped"}

    # ═══ PHASE 4: EXPRESS ═══
    if cfg.is_phase_enabled("express"):
        try:
            expressed = _run_with_retry(express, cfg, reflected, explored, phase_name="express")
            result["phases"]["express"] = {
                "status": "ok",
                "mood": expressed.get("mood", "unknown"),
                "insights": len(expressed.get("insights", [])),
                "data": expressed,
            }
        except Exception as e:
            result["phases"]["express"] = {"status": "error", "error": str(e)}
            expressed = None
    else:
        expressed = None
        result["phases"]["express"] = {"status": "skipped"}

    # ═══ PHASE 5: MEMORIZE (agent-scoped, full pipeline) ═══
    if cfg.is_phase_enabled("memorize"):
        try:
            # Use the REAL memorize() pipeline — LLM scoring + rule-based fallback + circuit edits.
            # Create agent-scoped config so all file paths resolve to agent's profile directory.
            from .config import EvolConfig
            agent_cfg = EvolConfig(profile=agent_profile, mode="per_agent")
            # Override edit_mode to "auto" so edits actually land
            agent_cfg.edit_mode = "auto"
            
            from .registry import memorize as _memorize
            memorized = _memorize(agent_cfg, reflected, expressed, explored)
            
            # Check if real pipeline produced meaningful output
            applied_count = len(memorized.get("applied", []))
            proposals_count = len(memorized.get("proposals", []))
            
            if applied_count == 0 and proposals_count == 0:
                # Real pipeline scored nothing — augment with lightweight log at minimum
                from .knowledge import memorize_agent
                fallback = memorize_agent(reflected, expressed, explored, agent_profile)
                memorized["applied"].extend(fallback.get("applied", []))
                memorized["_fallback_note"] = "real pipeline scored 0 items, augmented with lightweight log"
            
            result["phases"]["memorize"] = {
                "status": "ok",
                "applied": len(memorized.get("applied", [])),
                "proposals": len(memorized.get("proposals", [])),
                "data": memorized,
            }
        except Exception as e:
            # Real pipeline crashed — use lightweight fallback
            try:
                from .knowledge import memorize_agent
                memorized = memorize_agent(reflected, expressed, explored, agent_profile)
                result["phases"]["memorize"] = {
                    "status": "ok",
                    "applied": len(memorized.get("applied", [])),
                    "data": memorized,
                    "note": f"real pipeline crashed ({e}), used lightweight fallback",
                }
            except Exception as e2:
                result["phases"]["memorize"] = {"status": "error", "error": f"memorize failed: {e}, fallback: {e2}"}
    else:
        result["phases"]["memorize"] = {"status": "skipped"}

    # ── Touch markers ──
    try:
        if 'tracker' in dir():
            tracker.touch_per_agent_cycle(agent_profile)
    except Exception:
        pass

    result["duration_seconds"] = round(time.time() - t_start, 2)
    return result


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════

def _run_with_retry(phase_fn, cfg: EvolConfig, *args, phase_name: str, **kwargs) -> Any:
    """Run a phase function with retry logic."""
    last_error = None
    for attempt in range(cfg.max_retries_per_phase):
        try:
            return phase_fn(cfg, *args, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < cfg.max_retries_per_phase - 1:
                time.sleep(2 ** attempt)  # exponential backoff
    raise last_error  # type: ignore


def _should_run(cfg: EvolConfig) -> bool:
    """Check if enough time has passed since the last cycle."""
    marker = Path(cfg.profile_dir) / "evol" / ".last_cycle"
    if not marker.exists():
        return True

    try:
        last = float(marker.read_text().strip())
        elapsed = (time.time() - last) / 60  # minutes
        return elapsed >= cfg.cooldown_minutes
    except (ValueError, OSError):
        return True


def _express_can_run(cfg: EvolConfig) -> bool:
    """Check express cooldown."""
    marker = Path(cfg.profile_dir) / "evol" / ".last_express"
    if not marker.exists():
        return True

    try:
        last = float(marker.read_text().strip())
        elapsed = (time.time() - last) / 3600  # hours
        return elapsed >= cfg.express_cooldown_hours
    except (ValueError, OSError):
        return True


def _touch_last_cycle(cfg: EvolConfig):
    """Update the last cycle timestamp."""
    _touch_marker(cfg, "last_cycle")


def _touch_last_express(cfg: EvolConfig):
    """Update the last express timestamp."""
    _touch_marker(cfg, "last_express")


def _touch_marker(cfg: EvolConfig, name: str):
    """Generic marker file writer. Creates evol/{name} timestamp."""
    marker = Path(cfg.profile_dir) / "evol" / f".{name}"
    marker.parent.mkdir(parents=True, exist_ok=True)
    try:
        marker.write_text(str(time.time()))
    except OSError:
        pass


# ── Generic Phase Post-Hook ───────────────────────────────────────

PHASE_RESULT_KEYS = {
    # phase → list of top-level keys in the phase result dict
    "absorb": ["circuit_files", "session_summary", "timestamp"],
    "reflect": ["patterns", "signal_summary", "anomalies", "recommended_action"],
    "express": ["monologue", "mood", "insights", "portrait_prompt", "circuit_poem", "unanswered"],
    "explore": ["queries", "results", "discoveries"],
    "memorize": ["items", "applied", "proposals"],
}


def _run_phase_post_hook(cfg: EvolConfig, phase: str, phase_data: Dict[str, Any], cycle_result: Dict[str, Any]):
    """Execute a post-phase hook if configured for this phase.

    Hooks are configured in evol.json:
      "phase_post_commands": {"express": "python3 skills/evol/scripts/hooks/express-post.py --monologue \"$PHASE_monologue\" --json"}

    Respects notify_level:
      "off"   → no hooks fire
      "low"   → notification hooks only (reflect, explore, memorize), express video skipped
      "high"  → all hooks including express video

    Environment variables available to the hook:
      PHASE_RESULT_FILE  — path to temp JSON file with full phase data
      PHASE_{KEY}        — for each top-level key in the phase result (e.g. PHASE_monologue, PHASE_mood)
      EVOL_PROFILE       — the current profile name
      EVOL_PHASE         — the phase name
    """
    level = getattr(cfg, "notify_level", "low")

    # Filter by notify_level
    if level == "off":
        return

    cmd = cfg.phase_post_commands.get(phase, "")
    if not cmd:
        return

    # "low" mode: skip express video generation (expensive), keep notification hooks
    if level == "low" and phase == "express":
        log.info("phase_post_hook[%s]: skipped (notify_level=low, express video disabled)", phase)
        return

    import subprocess, tempfile

    log.info("phase_post_hook[%s]: running %s", phase, cmd[:80])

    # Write full phase data to a temp file (canonical source)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, prefix=f"evol-{phase}-") as f:
        json.dump(phase_data, f)
        result_file = f.name

    env = os.environ.copy()
    env["PHASE_RESULT_FILE"] = result_file
    env["EVOL_PROFILE"] = cfg.profile
    env["EVOL_PHASE"] = phase

    # Expose top-level keys as PHASE_{KEY} env vars
    known_keys = PHASE_RESULT_KEYS.get(phase, list(phase_data.keys()))
    for key in known_keys:
        val = phase_data.get(key)
        if val is not None:
            if isinstance(val, (list, dict)):
                env[f"PHASE_{key}"] = json.dumps(val)
            else:
                env[f"PHASE_{key}"] = str(val)[:4000]

    try:
        result = subprocess.run(
            ["bash", "-c", cmd],
            capture_output=True, text=True,
            timeout=180,
            env=env,
            cwd="/opt/data",
        )
        stdout = result.stdout.strip()
        stderr_tail = result.stderr.strip()[-300:] if result.stderr else ""
        log.info("phase_post_hook[%s]: rc=%s stdout=%s stderr=%s",
                 phase, result.returncode, stdout[:200], stderr_tail[:200])

        # Parse hook output into cycle result
        if stdout:
            hook_result = _parse_hook_output(stdout)
            if hook_result:
                phase_key = f"phases.{phase}.media"
                # Store under phases.{phase}.media in cycle result
                phase_result = cycle_result.setdefault("phases", {}).setdefault(phase, {})
                phase_result["media"] = hook_result

    except subprocess.TimeoutExpired:
        log.error("phase_post_hook[%s]: timeout (>180s)", phase)
    except Exception as e:
        log.error("phase_post_hook[%s]: %s", phase, e)
    finally:
        try:
            os.unlink(result_file)
        except OSError:
            pass


def _parse_hook_output(stdout: str) -> Dict[str, str]:
    """Parse hook stdout — JSON dict or file paths."""
    # Try JSON first
    try:
        data = json.loads(stdout)
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v and isinstance(v, str) and os.path.exists(v)}
    except (json.JSONDecodeError, ValueError):
        pass

    # Fall back to file path parsing
    media = {}
    for line in stdout.splitlines():
        line = line.strip()
        if line.endswith((".mp4", ".mp3", ".jpg", ".png", ".webp")):
            if line.startswith("MEDIA:"):
                line = line[6:]
            if os.path.exists(line):
                ext = os.path.splitext(line)[1]
                if ext == ".mp4":
                    media["video"] = line
                elif ext == ".mp3":
                    media["voice"] = line
                elif ext in (".jpg", ".png", ".webp"):
                    media["portrait"] = line
    return media


def disable(cfg=None):
    """Disable EVOL for a profile."""
    if cfg is None:
        cfg = EvolConfig()
    cfg.enabled = False
    cfg.save()
    return {"status": "ok", "profile": cfg.profile, "enabled": False}


def enable(cfg=None):
    """Enable EVOL for a profile."""
    if cfg is None:
        cfg = EvolConfig()
    cfg.enabled = True
    cfg.save()
    return {"status": "ok", "profile": cfg.profile, "enabled": True}


def set_edit_mode(mode: str, cfg=None):
    """Set edit mode: auto, suggested, or readonly."""
    if cfg is None:
        cfg = EvolConfig()
    if mode not in ("auto", "suggested", "readonly"):
        return {"status": "error", "error": f"Invalid mode: {mode}"}
    cfg.edit_mode = mode  # type: ignore
    cfg.save()
    return {"status": "ok", "profile": cfg.profile, "edit_mode": mode}


def set_phase_model(phase: str, provider: str = "", model: str = "", api_key: str = ""):
    """Configure model for a specific phase."""
    cfg = EvolConfig()
    if phase not in cfg.phase_models:
        return {"status": "error", "error": f"Unknown phase: {phase}"}
    pm = cfg.phase_models[phase]
    if provider:
        pm.provider = provider
    if model:
        pm.model = model
    if api_key:
        pm.api_key = api_key
    cfg.save()
    return {"status": "ok", "phase": phase, "provider": pm.provider, "model": pm.model}


def reset(profile: Optional[str] = None, clear_knowledge: bool = False, clear_history: bool = False) -> Dict[str, Any]:
    """Reset EVOL state for a profile — clean start from zero.
    
    Args:
        profile: Profile name (auto-detected if None)
        clear_knowledge: Also wipe ~/.hermes/knowledge/ (shared across profiles!)
        clear_history: Also wipe evol.jsonl and evol/proposals/
    
    Returns:
        {status, profile, wiped: [list of what was deleted]}
    """
    import shutil
    cfg = EvolConfig(profile=profile)
    wiped = []
    
    profile_dir = Path(cfg.profile_dir)
    evol_dir = profile_dir / "evol"
    
    # 1. Reset evol.json to defaults
    config_path = evol_dir / "evol.json"
    if config_path.exists():
        config_path.unlink()
        wiped.append(str(config_path))
    
    # Always wipe these markers
    for marker in [".last_cycle", ".last_express"]:
        mp = evol_dir / marker
        if mp.exists():
            mp.unlink()
            wiped.append(str(mp))
    
    # 2. Optionally clear cycle history
    if clear_history:
        log_path = profile_dir / "evol.jsonl"
        if log_path.exists():
            log_path.unlink()
            wiped.append(str(log_path))
        
        proposals_dir = evol_dir / "proposals"
        if proposals_dir.exists():
            shutil.rmtree(str(proposals_dir))
            wiped.append(str(proposals_dir))
    
    # 3. Optionally clear shared knowledge (DANGER ZONE)
    if clear_knowledge:
        kd = Path(os.path.expanduser("~/.hermes/knowledge"))
        if kd.exists():
            shutil.rmtree(str(kd))
            kd.mkdir(parents=True, exist_ok=True)
            wiped.append(str(kd) + " (ALL PROFILES)")
    
    # Regenerate fresh config
    fresh_cfg = EvolConfig(profile=cfg.profile)
    fresh_cfg.profile_dir = str(profile_dir)  # preserve explicit dir
    fresh_cfg.save()
    
    return {
        "status": "ok",
        "profile": cfg.profile,
        "wiped": wiped,
        "note": "EVOL reset to defaults. Will auto-detect provider/model from Hermes config on next cycle.",
    }


def status(profile: Optional[str] = None) -> Dict[str, Any]:
    """Get EVOL status for a profile."""
    cfg = EvolConfig(profile=profile)
    last_cycle_path = Path(cfg.profile_dir) / "evol" / ".last_cycle"
    last_express_path = Path(cfg.profile_dir) / "evol" / ".last_express"

    def _read_ts(p: Path) -> Optional[str]:
        try:
            ts = float(p.read_text().strip())
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except (ValueError, OSError):
            return None

    return {
        "profile": cfg.profile,
        "mode": cfg.mode,
        "enabled": cfg.enabled,
        "edit_mode": cfg.edit_mode,
        "phases": cfg.phase_enabled,
        "phase_models": {
            phase: {"provider": pm.provider or "hermes-default", "model": pm.model or "default"}
            for phase, pm in cfg.phase_models.items()
        },
        "cooldown": f"{cfg.cooldown_minutes}min",
        "express_cooldown": f"{cfg.express_cooldown_hours}h",
        "last_cycle": _read_ts(last_cycle_path),
        "last_express": _read_ts(last_express_path),
    }


# ═══════════════════════════════════════════════════════════════════
# EvolEngine Bridge — wraps module functions for gateway plugin.py API
# ═══════════════════════════════════════════════════════════════════

class EvolEngine:
    """Bridge class wrapping EVOL module functions into OOP API expected by plugin.py.

    plugin.py + commands.py expect:
      engine = EvolEngine(config)
      engine.status()    engine.material()    engine.get_config()
      engine.speak()     engine.reflect()     engine.explore()
      engine.full_cycle()    engine.start()
      engine._phase_state()  engine._get_prompts()
      engine._absorb_enabled, _reflect_enabled, etc.
    """

    def __init__(self, config: EvolConfig):
        self.cfg = config
        self.profile = config.profile
        self.mode = config.mode
        self._running = False
        self._thread: Optional[Any] = None
        self._cooldowns: Dict[str, float] = {}

        # Phase enable/disable — mutable toggles
        self._absorb_enabled = config.phase_enabled.get("absorb", True)
        self._reflect_enabled = config.phase_enabled.get("reflect", True)
        self._explore_enabled = config.phase_enabled.get("explore", True)
        self._express_enabled = config.phase_enabled.get("express", True)
        self._memorize_enabled = config.phase_enabled.get("memorize", True)
        self._heartbeat_enabled = True
        self._custom_prompts: Dict[str, str] = {}

        # Material buffer for absorb
        self._material_buffer: List[Dict] = []

        # Per-phase cascading counters: absorb→reflect→express→explore→memorize
        self._phase_counts: Dict[str, int] = {
            "reflect": 0,   # incremented by absorb ticks
            "express": 0,   # incremented by reflect completions
            "explore": 0,   # incremented by express completions
            "memorize": 0,  # incremented by explore completions
        }
        self._load_phase_counts()

    # ── Tool methods (return dicts — _wrap() in plugin.py serializes to JSON string) ──

    def status(self) -> Dict[str, Any]:
        return _build_status(self)

    def material(self) -> Dict[str, Any]:
        return {
            "profile": self.profile, "mode": self.mode,
            "buffer_size": len(self._material_buffer),
            "recent": self._material_buffer[-20:] if self._material_buffer else [],
            "gaps": [],
        }

    def get_config(self) -> Dict[str, Any]:
        return self.cfg.to_dict()

    def speak(self, force: bool = False) -> Dict[str, Any]:
        """Express phase — inner monologue + optional voice/portrait.
        Cascade: successful express → increment explore counter."""
        if not force and not self._express_enabled:
            return {"status": "skipped", "reason": "express disabled"}
        try:
            absorbed = {"profile": self.profile, "mode": self.mode, "circuit_files": {}}
            reflected = {"patterns": [], "anomalies": [], "bridge_signals": [], "circuit_health": {}}
            result = express(self.cfg, reflected)
            self._set_cooldown("express")
            # Post-phase hook (voice + portrait + video)
            _run_phase_post_hook(self.cfg, "express", result, {})
            # Cascade: express → increment explore counter
            self._phase_counts["explore"] = self._phase_counts.get("explore", 0) + 1
            self._save_phase_counts()
            return {"status": "ok", "data": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def reflect(self, force: bool = False) -> Dict[str, Any]:
        """Reflect phase — pattern synthesis from accumulated material."""
        if not force and not self._reflect_enabled:
            return {"status": "skipped", "reason": "reflect disabled"}
        try:
            # Feed real material buffer from heartbeat absorb ticks
            circuit_files = {}
            session_summary = ""
            if self._material_buffer:
                for tick in self._material_buffer:
                    if tick.get("type") == "absorb_tick":
                        for f in tick.get("files", []):
                            if f not in circuit_files:
                                circuit_files[f] = ""
                        session_summary += tick.get("summary", "")
            
            # Fallback: when buffer is empty (standalone call), read circuit files from disk
            if not circuit_files:
                import glob
                profile_dir = self.cfg.profile_dir
                for pattern in ["SOUL.md", "AGENTS.md", "MEMORY.md", "IDENTITY.md"]:
                    for p in [Path(profile_dir) / pattern, Path(profile_dir) / "evol" / pattern]:
                        if p.exists():
                            try:
                                circuit_files[p.name] = p.read_text()[:8000]
                            except Exception:
                                pass
                # Also grab recent evol.jsonl entries for context
                evol_log = Path(profile_dir) / "evol" / "evol.jsonl"
                if evol_log.exists():
                    try:
                        lines = evol_log.read_text().strip().split("\n")[-5:]
                        session_summary = "\n".join(l for l in lines if l.strip())
                    except Exception:
                        pass
            
            absorbed = {
                "profile": self.profile,
                "mode": self.mode,
                "circuit_files": circuit_files,
                "session_summary": session_summary,
            }
            result = reflect(self.cfg, absorbed)
            self._set_cooldown("reflect")
            # Cascade: successful reflect → increment express counter
            self._phase_counts["express"] = self._phase_counts.get("express", 0) + 1
            self._save_phase_counts()
            # Write .last_reflect marker for chain detection
            _touch_marker(self.cfg, "last_reflect")
            # Clear material buffer after successful reflect
            self._material_buffer.clear()
            return {"status": "ok", "data": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def explore(self, force: bool = False, query: str = "") -> Dict[str, Any]:
        """Explore phase — search gaps discovered in reflect.
        Cascade: successful explore → increment memorize counter."""
        if not force and not self._explore_enabled:
            return {"status": "skipped", "reason": "explore disabled"}
        try:
            reflected = {"patterns": [], "anomalies": [], "bridge_signals": []}
            result = explore(self.cfg, reflected)
            self._set_cooldown("explore")
            # Cascade: explore → increment memorize counter
            self._phase_counts["memorize"] = self._phase_counts.get("memorize", 0) + 1
            self._save_phase_counts()
            return {"status": "ok", "data": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def full_cycle(self, force: bool = False) -> Dict[str, Any]:
        """Run complete EVOL cycle: absorb→reflect→explore→express→memorize."""
        if not force and not self._should_run():
            return {"status": "skipped", "reason": "cooldown"}
        try:
            result = run_cycle(profile=self.profile, mode=self.mode, force=force)
            self._set_cooldown("cycle")
            return {"status": "ok", "data": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def memorize(self, force: bool = False, manual: bool = False) -> Dict[str, Any]:
        """Standalone memory consolidation — score findings, adjust weights,
        promote to Knowledge wiki, edit circuit, demote stale, detect cross-cycle patterns.
        
        When manual=True (triggered via /evol memorize): forces edit_mode="suggested"
        so circuit edits are proposed but never auto-applied."""
        if not force and not self._check_cooldown("memorize"):
            return {"status": "skipped", "reason": "cooldown"}
        try:
            from hermes_evol.registry import memorize as _memorize
            reflected = {"patterns": [], "anomalies": [], "bridge_signals": []}
            expressed = None
            explored = {"discoveries": [], "queries": []}
            # Manual trigger → suggestion-only, prevent auto-application
            if manual:
                saved_mode = self.cfg.edit_mode
                self.cfg.edit_mode = "suggested"
            result = _memorize(self.cfg, reflected, expressed, explored)
            if manual:
                self.cfg.edit_mode = saved_mode
            self._set_cooldown("memorize")
            if manual:
                # Return formatted human-readable string (bypasses json.dumps)
                return _format_memorize_result(result, mode="suggested")
            return {"status": "ok", "data": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def task_end(self, session_id: str = "", profile: str = "") -> Dict[str, Any]:
        """Session-mode EVOL — single-shot cycle for subagent task completion.
        
        Called by coder/reviewer/analyst/etc. after completing a task.
        Runs absorb→reflect→express→explore→memorize immediately.
        No heartbeat. No cascade. No idle depth.
        Writes to role MEMORY.md, skills, evol.jsonl. Never conductor circuit.
        
        Per-agent v2: when threshold met (>3 tool calls AND >2000 tokens),
        fires a per-agent EVOL cycle scoped to that agent only.
        
        Args:
            session_id: Optional session ID to attach to cycle record
            profile: Override profile name. Subagents MUST pass their own profile
                     (e.g., "coder", "analyst", "reviewer") to write to their
                     own MEMORY.md and evol.jsonl. Defaults to configured profile.
        """
        try:
            target_profile = profile or self.profile
            
            # ── Per-agent EVOL v2: completion-count threshold ──
            from .stores import AgentSessionTracker
            tracker = AgentSessionTracker()
            
            # Always record this completion (session end → write JSONL)
            # Use a synthetic "session" with completion marker — the tracker
            # counts completions as entries in the JSONL file.
            tracker.start_session(target_profile)
            tracker.record_tool_call(target_profile)  # mark that work happened
            tracker.end_session(target_profile)
            
            min_completions = getattr(self.cfg, 'per_agent_min_completions', 3)
            cooldown_h = self.cfg.per_agent_cooldown_hours
            
            if tracker.check_threshold(target_profile, min_completions, cooldown_h):
                # Fire per-agent EVOL cycle
                log.info("task_end: per-agent threshold met for %s (%d completions) → firing per_agent_cycle",
                         target_profile, min_completions)
                return run_per_agent_cycle(agent_profile=target_profile, cfg=self.cfg)
            
            # Below threshold → standard session-mode cycle
            result = run_session_cycle(profile=target_profile, session_id=session_id or None)
            return {"status": "ok", "data": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ── Proposal Management ──

    def list_proposals(self) -> str:
        """List pending proposals in human-readable format."""
        prop_dir = Path(self.profile_dir) / "evol" / "proposals"
        if not prop_dir.exists():
            return "No proposals found. Run /evol memorize to generate them."

        proposals = sorted(prop_dir.glob("proposal-*.json"))
        if not proposals:
            return "No pending proposals."

        out = ["📋 *Pending Proposals*", ""]
        for i, pf in enumerate(proposals):
            try:
                data = json.loads(pf.read_text())
                target = data.get("target", "?")
                weight = data.get("weight", 0)
                concept = data.get("concept", "?")
                text = data.get("text", "")[:150]
                ts = data.get("timestamp", "?")
                out.append(f"  #{i+1} [{pf.name}]")
                out.append(f"     → {target} (wt:{weight:.2f})")
                out.append(f"     {concept[:80]}")
                if text:
                    out.append(f"     | {text[:120]}")
                out.append("")
            except Exception:
                out.append(f"  #{i+1} [{pf.name}] — unreadable")
                out.append("")

        out.append("Use /evol proposals accept <#> to apply, /evol proposals reject <#> to delete")
        out.append("Or /evol proposals accept-all / reject-all")
        return "\n".join(out)

    def accept_proposal(self, prop_id: str) -> str:
        """Accept and apply a specific proposal by index number or filename."""
        from pathlib import Path as _Path
        prop_dir = _Path(self.profile_dir) / "evol" / "proposals"
        if not prop_dir.exists():
            return "No proposals found."

        proposals = sorted(prop_dir.glob("proposal-*.json"))
        if not proposals:
            return "No pending proposals."

        # Resolve index or filename
        try:
            idx = int(prop_id) - 1
            if 0 <= idx < len(proposals):
                pf = proposals[idx]
            else:
                return f"Invalid proposal number. Range: 1–{len(proposals)}"
        except ValueError:
            pf = prop_dir / prop_id
            if not pf.exists():
                return f"Proposal not found: {prop_id}"

        try:
            data = json.loads(pf.read_text())
            target = data.get("target", "")
            text = data.get("text", "")
            concept = data.get("concept", "")
            weight = data.get("weight", 0)

            if not target or not text:
                pf.unlink()
                return f"❌ {pf.name}: missing target/text — deleted"

            from .registry import _apply_circuit_edit
            success = _apply_circuit_edit(
                self.cfg, target, text, "append",
                concept=concept, weight=weight
            )
            if success:
                pf.unlink()
                return f"✅ Accepted {pf.name}: {target}"
            return f"❌ Failed to apply {pf.name}: {target}"
        except Exception as e:
            return f"❌ Error: {e}"

    def reject_proposal(self, prop_id: str) -> str:
        """Reject and delete a specific proposal by index number or filename."""
        from pathlib import Path as _Path
        prop_dir = _Path(self.profile_dir) / "evol" / "proposals"
        if not prop_dir.exists():
            return "No proposals found."

        proposals = sorted(prop_dir.glob("proposal-*.json"))
        if not proposals:
            return "No pending proposals."

        try:
            idx = int(prop_id) - 1
            if 0 <= idx < len(proposals):
                pf = proposals[idx]
            else:
                return f"Invalid proposal number. Range: 1–{len(proposals)}"
        except ValueError:
            pf = prop_dir / prop_id
            if not pf.exists():
                return f"Proposal not found: {prop_id}"

        try:
            pf.unlink()
            return f"🗑️ Rejected {pf.name}"
        except OSError as e:
            return f"❌ Could not delete: {e}"

    def accept_all_proposals(self) -> str:
        """Accept and apply all pending proposals."""
        prop_dir = Path(self.profile_dir) / "evol" / "proposals"
        if not prop_dir.exists():
            return "No proposals to accept."

        proposals = sorted(prop_dir.glob("proposal-*.json"))
        if not proposals:
            return "No pending proposals."

        accepted = []
        failed = []
        for pf in proposals:
            try:
                data = json.loads(pf.read_text())
                target = data.get("target", "")
                text = data.get("text", "")
                concept = data.get("concept", "")
                weight = data.get("weight", 0)

                if not target or not text:
                    pf.unlink()
                    failed.append(f"{pf.name}: missing target/text")
                    continue

                # Apply via registry's upsert logic
                from .registry import _apply_circuit_edit
                success = _apply_circuit_edit(
                    self.cfg, target, text, "append",
                    concept=concept, weight=weight
                )
                if success:
                    pf.unlink()
                    accepted.append(f"{target}")
                else:
                    failed.append(f"{target}: write failed")
            except Exception as e:
                failed.append(f"{pf.name}: {e}")

        out = []
        if accepted:
            out.append(f"✅ Accepted {len(accepted)}: {', '.join(accepted)}")
        if failed:
            out.append(f"❌ Failed {len(failed)}: {'; '.join(failed)}")
        return "\n".join(out) if out else "Nothing to do."

    def reject_all_proposals(self) -> str:
        """Reject and delete all pending proposals."""
        prop_dir = Path(self.profile_dir) / "evol" / "proposals"
        if not prop_dir.exists():
            return "No proposals to reject."

        proposals = list(prop_dir.glob("proposal-*.json"))
        count = 0
        for pf in proposals:
            try:
                pf.unlink()
                count += 1
            except OSError:
                pass
        return f"🗑️ Rejected {count} proposal(s)."

    # ── Lifecycle ──

    def start(self):
        """Start background heartbeat thread (daemon, auto-cleaned on gateway exit)."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop heartbeat thread."""
        self._running = False

    # ── Phase state (for commands.py) ──

    def _phase_state(self) -> Dict[str, Any]:
        return {
            "absorb": self._absorb_enabled,
            "reflect": self._reflect_enabled,
            "explore": self._explore_enabled,
            "express": self._express_enabled,
            "memorize": self._memorize_enabled,
            "heartbeat": self._heartbeat_enabled,
            "mode": self.mode,
        }

    def _get_prompts(self) -> Dict[str, str]:
        return dict(self._custom_prompts)

    def set_notify_level(self, level: str) -> Dict[str, Any]:
        """Set notification level: off | low | high."""
        if level not in ("off", "low", "high"):
            return {"status": "error", "error": f"Invalid level: {level}", "valid": ["off", "low", "high"]}
        self.cfg.notify_level = level
        self.cfg.save()
        return {"status": "ok", "notify_level": level, "description": {
            "off": "No hooks fire — silent operation",
            "low": "Notifications only (reflect/explore/memorize) — express video skipped",
            "high": "All hooks including express video generation",
        }[level]}

    # ── Heartbeat ──

    def _heartbeat_loop(self):
        """Probe every 15min, absorb material, evaluate multi-gate triggers."""
        while self._running:
            try:
                self._absorb_tick()
                self._evaluate_all_triggers()
            except Exception:
                pass
            time.sleep(900)  # probe every 15 minutes regardless of cooldowns

    def _evaluate_all_triggers(self):
        """Cascading accumulator triggers — each phase counts up to its threshold,
        then fires the NEXT phase downstream. Organic cascade, not full chain blast.
        
        Flow:
        absorb ticks → reflect_counter++ → reflect fires → express_counter++
        express fires → explore_counter++ → explore fires → memorize_counter++
        memorize fires → circuit adapted
        
        Thresholds are per-phase configurable via evol.json phase_triggers dict.
        """
        thr = self.cfg.phase_triggers  # per-phase thresholds
        
        # G1: Absorb → Reflect
        if self._phase_counts.get("reflect", 0) >= thr.get("reflect", 3) and self._check_cooldown("reflect"):
            self._phase_counts["reflect"] = 0
            self._save_phase_counts()
            self.reflect(force=True)
            return
        
        # G2: Reflect → Express
        if self._phase_counts.get("express", 0) >= thr.get("express", 3) and self._check_cooldown("express"):
            self._phase_counts["express"] = 0
            self._save_phase_counts()
            self.speak(force=True)
            return
        
        # G3: Express → Explore
        if self._phase_counts.get("explore", 0) >= thr.get("explore", 3) and self._check_cooldown("explore"):
            self._phase_counts["explore"] = 0
            self._save_phase_counts()
            self.explore(force=True)
            return
        
        # G4: Explore → Memorize
        if self._phase_counts.get("memorize", 0) >= thr.get("memorize", 3) and self._check_cooldown("memorize"):
            self._phase_counts["memorize"] = 0
            self._save_phase_counts()
            self.memorize(force=True)
            return
        
        # G5: Activity-based — kanban tasks completed
        if self._activity_since_last_cycle() and self._check_cooldown("reflect"):
            self.reflect(force=True)
            return
        
        # G6: Idle-based — organism dormant, guaranteed daily cycle (ALL profiles)
        if self._idle_long_enough() and self._check_cooldown("express"):
            result = run_cycle(profile=self.profile, mode="global", force=True)
            self._set_cooldown("cycle")
            return

        # G7: Per-agent auto-trigger — scan ALL agent trackers, fire when threshold met
        if self._per_agent_auto_trigger():
            return

    def _per_agent_auto_trigger(self) -> bool:
        """Scan all agent profiles, fire per-agent EVOL when >=3 session ends detected.
        
        Runs every heartbeat tick (15m). Agent-tracker-independent — no agent
        needs to call evol_task_end(). The heartbeat detects session completions
        in tracker JSONL files and fires automatically.
        
        Returns True if any agent cycle was fired (so caller can return early).
        """
        try:
            from .stores import AgentSessionTracker
            tracker = AgentSessionTracker()
            profiles = self.cfg.global_profiles or self.cfg._discover_profiles()
            
            for prof in profiles:
                if prof == self.profile:
                    continue  # skip conductor self
                try:
                    min_c = getattr(self.cfg, 'per_agent_min_completions', 3)
                    cooldown_h = getattr(self.cfg, 'per_agent_cooldown_hours', 4)
                    if tracker.check_threshold(prof, min_c, cooldown_h):
                        log.info("G7 auto-trigger: %s threshold met (%d completions) → firing per_agent_cycle", 
                                 prof, min_c)
                        run_per_agent_cycle(agent_profile=prof, cfg=self.cfg)
                        return True
                except Exception:
                    pass
        except Exception:
            pass
        return False

    def _activity_since_last_cycle(self) -> bool:
        """Check if kanban tasks completed since last EVOL cycle."""
        marker = Path(self.cfg.profile_dir) / "evol" / ".last_cycle"
        if not marker.exists():
            return False
        try:
            last_ts = float(marker.read_text().strip())
            kanban_db = Path(os.path.expanduser("~/.hermes/kanban/kanban.db"))
            if not kanban_db.exists():
                return False
            import sqlite3
            conn = sqlite3.connect(f"file:{kanban_db}?mode=ro", uri=True)
            cursor = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE status='done' AND completed_at > ?",
                (last_ts,))
            count = cursor.fetchone()[0]
            conn.close()
            return count >= self.cfg.activity_trigger_tasks
        except Exception:
            return False

    def _idle_long_enough(self) -> bool:
        """Check if organism has been idle long enough for guaranteed cycle."""
        marker = Path(self.cfg.profile_dir) / "evol" / ".last_cycle"
        if not marker.exists():
            return True
        try:
            last_ts = float(marker.read_text().strip())
            hours_since = (time.time() - last_ts) / 3600
            return hours_since >= self.cfg.fallback_cycle_hours
        except Exception:
            return True

    def _reflect_just_completed(self) -> bool:
        """Check if reflect phase just ran (own marker, not .last_cycle)."""
        marker = Path(self.cfg.profile_dir) / "evol" / ".last_reflect"
        if not marker.exists():
            return False
        try:
            last_ts = float(marker.read_text().strip())
            return (time.time() - last_ts) < 3600  # within past hour
        except Exception:
            return False

    def _absorb_tick(self):
        """Collect material, increment reflect counter for cascade."""
        try:
            from .registry import absorb as _absorb
            absorbed = _absorb(self.cfg)
            files = list(absorbed.get("circuit_files", {}).keys())
            summary = absorbed.get("session_summary", "")
            if files or summary:
                self._material_buffer.append({
                    "ts": _utc_now(),
                    "type": "absorb_tick",
                    "files": files,
                    "summary": summary[:2000],
                })
                # Each absorb tick feeds the reflect cascade
                self._phase_counts["reflect"] = self._phase_counts.get("reflect", 0) + 1
                self._save_phase_counts()
        except ImportError:
            from registry import absorb as _absorb
            absorbed = _absorb(self.cfg)
            files = list(absorbed.get("circuit_files", {}).keys())
            summary = absorbed.get("session_summary", "")
            if files or summary:
                self._material_buffer.append({
                    "ts": _utc_now(),
                    "type": "absorb_tick",
                    "files": files,
                    "summary": summary[:2000],
                })
                self._phase_counts["reflect"] = self._phase_counts.get("reflect", 0) + 1
                self._save_phase_counts()

    # ── Phase Counter Persistence ──

    def _counts_path(self) -> Path:
        return Path(self.cfg.profile_dir) / "evol" / ".phase_counts.json"

    def _save_phase_counts(self):
        """Persist cascading counters to disk."""
        try:
            p = self._counts_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self._phase_counts))
        except (OSError, IOError):
            pass

    def _load_phase_counts(self):
        """Restore cascading counters from disk on startup."""
        try:
            p = self._counts_path()
            if p.exists():
                loaded = json.loads(p.read_text())
                self._phase_counts.update(loaded)
        except (json.JSONDecodeError, OSError, IOError):
            pass  # Use defaults

    # ── Cooldown ──

    def _should_run(self) -> bool:
        marker = Path(self.cfg.profile_dir) / "evol" / ".last_cycle"
        if not marker.exists():
            return True
        try:
            last = float(marker.read_text().strip())
            return (time.time() - last) / 60 >= self.cfg.cooldown_minutes
        except (ValueError, OSError):
            return True

    def _check_cooldown(self, phase: str) -> bool:
        cooldown_hours = getattr(self.cfg, f"{phase}_cooldown_hours", 4) if phase != "cycle" else 0
        if phase == "reflect":
            cooldown_hours = 4
        elif phase == "express":
            cooldown_hours = self.cfg.express_cooldown_hours
        last = self._cooldowns.get(phase, 0)
        return (time.time() - last) > (cooldown_hours * 3600)

    def _set_cooldown(self, phase: str):
        self._cooldowns[phase] = time.time()


def _format_memorize_result(result: Dict[str, Any], mode: str = "auto") -> str:
    """One-liner output — no boilerplate, no JSON, no repetition."""
    items = result.get("items", [])
    proposals = result.get("proposals", [])
    evol_entries = result.get("evol_log_entries", 0)
    
    out = [f"🧠 *MEMORIZE — {mode.upper()}*"]
    
    if not items and not proposals:
        return "\n".join(out) + "\nNo findings."
    
    # Deduplicate by concept (case-insensitive) — highest weight wins
    seen = {}
    for item in items:
        desc = item.get("description", "").strip().lower()
        wt = item.get("raw_weight", 0)
        if desc and (desc not in seen or wt > seen[desc]["raw_weight"]):
            seen[desc] = item
    unique = list(seen.values())
    
    dropped = len(items) - len(unique)
    
    for item in unique:
        wt = item.get("raw_weight", 0)
        target = item.get("target", "?")
        desc = item.get("description", "?")
        icon = "🔴" if wt >= 0.85 else "🟡" if wt >= 0.65 else "🟢"
        out.append(f"{icon} wt:{wt:.2f} → {target}  {desc}")
    
    if dropped:
        out.append(f"  ⚡ {dropped} duplicates merged")
    
    if mode == "suggested":
        out.append(f"\n📋 {len(proposals)} proposals → /evol proposals to review")
    
    n_entries = len(evol_entries) if isinstance(evol_entries, list) else evol_entries
    out.append(f"📊 {n_entries} log entries")
    
    return "\n".join(out)

def _build_status(engine: Any) -> Dict[str, Any]:
    """Build condensed EVOL status — per-phase readiness, trigger status, next milestone."""
    now = time.time()
    markers_dir = Path(engine.cfg.profile_dir) / "evol"
    
    def _read_ts(name: str) -> Optional[float]:
        p = markers_dir / f".{name}"
        try:
            return float(p.read_text().strip())
        except Exception:
            return None
    
    def _fmt_ago(ts: Optional[float]) -> str:
        if ts is None:
            return "never"
        sec = now - ts
        if sec < 60:
            return f"{int(sec)}s ago"
        elif sec < 3600:
            return f"{int(sec/60)}m ago"
        elif sec < 86400:
            return f"{int(sec/3600)}h ago"
        return f"{int(sec/86400)}d ago"
    
    def _cooldown_ready(phase: str, cooldown_sec: float) -> str:
        last = engine._cooldowns.get(phase, 0)
        if last == 0:
            return "✅ ready"
        elapsed = now - last
        if elapsed >= cooldown_sec:
            return "✅ ready"
        remaining = cooldown_sec - elapsed
        if remaining < 60:
            return f"⏳ {int(remaining)}s"
        elif remaining < 3600:
            return f"⏳ {int(remaining/60)}m"
        return f"⏳ {int(remaining/3600)}h"
    
    # Absorb → Reflect cascade
    thr = engine.cfg.phase_triggers
    reflect_ct = engine._phase_counts.get("reflect", 0)
    express_ct = engine._phase_counts.get("express", 0)
    explore_ct = engine._phase_counts.get("explore", 0)
    memorize_ct = engine._phase_counts.get("memorize", 0)
    
    # Absorb state
    buffer_len = len(engine._material_buffer)
    last_absorb = _read_ts("last_cycle")  # approximate
    
    # Reflect state
    last_reflect = _read_ts("last_reflect")
    reflect_cd = _cooldown_ready("reflect", 4 * 3600)
    
    # Express state
    last_express = _read_ts("last_express") or engine._cooldowns.get("express", 0)
    if not (isinstance(last_express, (int, float)) and last_express > 1700000000):
        last_express = engine._cooldowns.get("express", 0)
    express_cd = _cooldown_ready("express", engine.cfg.express_cooldown_hours * 3600)
    
    # Explore state
    last_explore = engine._cooldowns.get("explore", 0)
    explore_cd = _cooldown_ready("explore", 4 * 3600)
    
    # Memorize state
    last_memorize = engine._cooldowns.get("memorize", 0)
    memorize_cd = _cooldown_ready("memorize", 4 * 3600)
    
    # Next trigger estimate
    triggers = []
    if reflect_ct < thr.get("reflect", 3):
        triggers.append(f"need {thr['reflect'] - reflect_ct} more absorb ticks → reflect")
    if express_ct < thr.get("express", 3) and reflect_cd.startswith("✅"):
        triggers.append(f"need {thr['express'] - express_ct} more reflects → express")
    if explore_ct < thr.get("explore", 3) and express_cd.startswith("✅"):
        triggers.append(f"need {thr['explore'] - explore_ct} more expresses → explore")
    if memorize_ct < thr.get("memorize", 3) and explore_cd.startswith("✅"):
        triggers.append(f"need {thr['memorize'] - memorize_ct} more explores → memorize")
    
    return {
        "engine": "hermes-evol",
        "version": "0.5.2",
        "profile": engine.profile,
        "mode": engine.mode,
        "heartbeat": engine._running,
        "cascade": {
            "absorb→reflect": f"{reflect_ct}/{thr.get('reflect', 3)}",
            "reflect→express": f"{express_ct}/{thr.get('express', 3)}",
            "express→explore": f"{explore_ct}/{thr.get('explore', 3)}",
            "explore→memorize": f"{memorize_ct}/{thr.get('memorize', 3)}",
        },
        "flow": {
            "absorb":  {"buffer": str(buffer_len), "last": _fmt_ago(last_absorb)},
            "reflect":    {"status": reflect_cd, "last": _fmt_ago(last_reflect)},
            "explore":    {"status": explore_cd, "last": _fmt_ago(last_explore if isinstance(last_explore, (int, float)) and last_explore > 100000 else None)},
            "express":    {"status": express_cd, "last": _fmt_ago(last_express if isinstance(last_express, (int, float)) and last_express > 100000 else None)},
            "memorize":   {"status": memorize_cd, "last": _fmt_ago(last_memorize if isinstance(last_memorize, (int, float)) and last_memorize > 100000 else None)},
        },
        "triggers": triggers or ["waiting for cooldowns"],
        "chain_active": bool(last_reflect and (now - last_reflect) < 600),
    }
