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
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

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
        if not _express_can_run(cfg):
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
                # Update last express timestamp
                _touch_last_express(cfg)
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
        except Exception as e:
            result["phases"]["memorize"] = {"status": "error", "error": str(e)}
    else:
        result["phases"]["memorize"] = {"status": "skipped"}

    # ── Finalize ──
    _touch_last_cycle(cfg)
    _append_evol_jsonl(cfg, result)
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
    _append_evol_jsonl(cfg, result)
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

    # Role circuit files only (MEMORY.md for this role)
    for fname in ["MEMORY.md"]:
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


def _append_evol_jsonl(cfg: EvolConfig, cycle_result: Dict[str, Any]):
    """Append a cycle result to the profile's evol.jsonl."""
    log_path = Path(cfg.profile_dir) / "evol.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": time.time(),
        "type": cycle_result.get("mode", "cycle"),
        "profile": cfg.profile,
        "operation_mode": cfg.operation_mode,
        "duration_seconds": cycle_result.get("duration_seconds", 0),
        "phases": cycle_result.get("phases", {}),
        "status": cycle_result.get("status", "error"),
    }
    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


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

    def memorize(self, force: bool = False) -> Dict[str, Any]:
        """Standalone memory consolidation — score findings, adjust weights,
        promote to Knowledge wiki, edit circuit, demote stale, detect cross-cycle patterns."""
        if not force and not self._check_cooldown("memorize"):
            return {"status": "skipped", "reason": "cooldown"}
        try:
            from hermes_evol.registry import memorize as _memorize
            reflected = {"patterns": [], "anomalies": [], "bridge_signals": []}
            expressed = None
            explored = {"discoveries": [], "queries": []}
            result = _memorize(self.cfg, reflected, expressed, explored)
            self._set_cooldown("memorize")
            return {"status": "ok", "data": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def task_end(self, session_id: str = "") -> Dict[str, Any]:
        """Session-mode EVOL — single-shot cycle for subagent task completion.
        
        Called by coder/reviewer/analyst/etc. after completing a task.
        Runs absorb→reflect→express→explore→memorize immediately.
        No heartbeat. No cascade. No idle depth.
        Writes to role MEMORY.md, skills, evol.jsonl. Never conductor circuit.
        """
        try:
            result = run_session_cycle(profile=self.profile, session_id=session_id or None)
            return {"status": "ok", "data": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

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
        
        # G6: Idle-based — organism dormant, guaranteed daily cycle
        if self._idle_long_enough() and self._check_cooldown("express"):
            self.full_cycle(force=True)
            return

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


def _build_status(engine: EvolEngine) -> Dict[str, Any]:
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
        "version": "0.4.2",
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
