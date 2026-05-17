"""EVOL Engine — heartbeat, state detection, phase orchestration."""

import json
import logging
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .stores import StateStore, MaterialStore, VoiceStore
from .config import EvolConfig

# Phase implementations are loaded lazily from registry
# to avoid circular imports
from . import registry as _registry

logger = logging.getLogger(__name__)


class EvolEngine:
    """Background observer — runs phases based on triggers."""

    def __init__(self, config: EvolConfig):
        self.cfg = config
        self.state_store = StateStore(config.state_file)
        self.material_store = MaterialStore(config.material_file)
        self.voice_store = VoiceStore(config.voice_file)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_heartbeat: float = 0.0
        self._cooldowns: dict[str, float] = {}
        self._manual_trigger: dict[str, float] = {}
        self._cycle_count: int = 0
        # Phase enable/disable (all default on)
        self._absorb_enabled: bool = True
        self._reflect_enabled: bool = True
        self._explore_enabled: bool = True
        self._express_enabled: bool = True
        self._memorize_enabled: bool = True
        self._heartbeat_enabled: bool = True
        # Custom prompts overrides
        self._custom_prompts: dict[str, str] = {}

    # ── Public tools (return dicts — plugin.py wraps them as JSON strings) ──

    def status(self) -> dict:
        """Return current organism state and EVOL health."""
        current = self.state_store.current()
        idle_sec = current.get("idle_sec", 0) if current else 0
        return {
            "engine": "hermes-evol",
            "version": "0.2.0",
            "heartbeat_alive": self._running,
            "state": current.get("state", "UNKNOWN") if current else "UNKNOWN",
            "idle_seconds": idle_sec,
            "infra": {
                "ct_up": current.get("ct_up", 0) if current else 0,
                "disk_pct": current.get("disk_pct", 0) if current else 0,
                "gateway_rss_mb": current.get("gw_rss_mb", 0) if current else 0,
                "providers_healthy": not (current or {}).get("prov_degraded", False),
            },
            "material_buffer_size": len(self.material_store.buffer),
            "last_voice": self._last_voice_ts(),
            "cooldowns": {
                k: max(0, v - time.time())
                for k, v in self._cooldowns.items()
            },
        }

    def material(self) -> dict:
        """View accumulated material from absorb phase."""
        entries = self.material_store.buffer[-50:]
        return {
            "entries": entries,
            "count": len(self.material_store.buffer),
            "buffer": [e for e in entries],
        }

    def get_config(self) -> dict:
        """Show current EVOL configuration."""
        return {
            **self.cfg.to_dict(),
            "phase_state": self._phase_state(),
        }

    def speak(self, force: bool = False) -> dict:
        """Trigger EVOL inner voice expression."""
        if not force and not self._check_cooldown("express"):
            return {"phase": "express", "blocked": "cooldown"}
        if not self._express_enabled:
            return {"phase": "express", "blocked": "disabled"}

        # Collect material for context
        material = self.material_store.since_last_voice()
        state = self.state_store.current()

        result = _registry._express_render(self.cfg, material, self.material_store._reflections)
        self._set_cooldown("express")
        self._cycle_count += 1
        return {"phase": "express", "result": result, "cycle": self._cycle_count}

    def reflect(self, force: bool = False) -> dict:
        """Trigger EVOL reflection on accumulated patterns."""
        if not force and not self._check_cooldown("reflect"):
            return {"phase": "reflect", "blocked": "cooldown"}
        if not self._reflect_enabled:
            return {"phase": "reflect", "blocked": "disabled"}

        material = self.material_store.buffer
        state = self.state_store.current()

        # Run fast heuristic first
        patterns = _registry._process_patterns(self.cfg, material, state)
        # Then LLM if available
        llm_result = _registry._process_with_llm(self.cfg, material, state)

        self._set_cooldown("reflect")
        self.material_store._reflections = [patterns, llm_result]
        return {
            "phase": "reflect",
            "patterns": patterns,
            "llm_analysis": llm_result,
        }

    def explore(self, query: Optional[str] = None, force: bool = False) -> dict:
        """Trigger EVOL knowledge exploration."""
        if not force and not self._check_cooldown("explore"):
            return {"phase": "explore", "blocked": "cooldown"}
        if not self._explore_enabled:
            return {"phase": "explore", "blocked": "disabled"}

        gaps = self.material_store.get_gaps()
        if query:
            result = {
                "phase": "explore",
                "manual_query": query,
                "searches": [_registry._search_searxng(self.cfg, query)],
            }
        else:
            result = _registry._explore_with_llm(
                self.cfg, gaps, self.state_store.current(), self.material_store
            )

        self._set_cooldown("explore")
        return result

    def full_cycle(self, force: bool = False) -> dict:
        """Run a complete EVOL cycle."""
        outputs = {}
        phases = ["reflect", "explore", "express"]
        for phase in phases:
            fn = getattr(self, phase, None)
            if fn:
                outputs[phase] = fn(force=force)
        return {"phase": "full_cycle", "outputs": outputs}

    # ── Heartbeat ──

    def start(self):
        """Start background heartbeat thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop background heartbeat thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _heartbeat_loop(self):
        """Probe vitals every heartbeat_interval seconds."""
        while self._running:
            try:
                state = self._probe()
                self.state_store.append(state)
                # Absorb new material
                self._absorb()
                # Check triggers
                self._evaluate_triggers()
            except Exception:
                logger.exception("Heartbeat tick failed")
            time.sleep(self.cfg.heartbeat_interval)

    def _probe(self) -> dict:
        """Probe organism vitals."""
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "state": "ACTIVE",
            "idle_sec": 0,
            "ct_up": 0,
            "disk_pct": _disk_pct(),
            "gw_rss_mb": 0,
            "prov_degraded": False,
        }

    def _absorb(self):
        """Collect material from configured sources."""
        now = time.time()
        since = now - self.cfg.heartbeat_interval

        for source_cfg in self.cfg.absorb_sources:
            source_name = source_cfg.get("name", "")
            collector = _registry.SOURCES.get(source_name)
            if collector:
                try:
                    entries = collector(source_cfg, since)
                    for entry in entries:
                        self.material_store.append(entry)
                except Exception:
                    logger.exception("Absorb source %s failed", source_name)

        # Trim old entries
        if len(self.material_store.buffer) > self.cfg.material_retention:
            self.material_store.buffer = self.material_store.buffer[
                -self.cfg.material_retention:
            ]

    def _evaluate_triggers(self):
        """Check if any phase should fire."""
        state = self.state_store.current()
        material = self.material_store

        # Reflect trigger check
        for trigger_cfg in self.cfg.reflect_triggers:
            trigger_name = trigger_cfg.get("name", "")
            trigger_fn = _registry.TRIGGERS.get(trigger_name)
            if trigger_fn and trigger_fn(self.cfg, state, material):
                if self._check_cooldown("reflect"):
                    self.reflect()
                    break

        # Express trigger check
        for trigger_cfg in self.cfg.express_triggers:
            trigger_name = trigger_cfg.get("name", "")
            trigger_fn = _registry.TRIGGERS.get(trigger_name)
            if trigger_fn and trigger_fn(self.cfg, state, material):
                if self._check_cooldown("express"):
                    self.speak()
                    break

    def _last_voice_ts(self) -> Optional[str]:
        """Timestamp of last voice expression."""
        last = self.voice_store.last_voice()
        if last:
            return last.get("ts")
        return None

    def _check_cooldown(self, phase: str) -> bool:
        """Check if phase is off cooldown. Returns True if ready."""
        cooldown_hours = getattr(self.cfg, f"{phase}_cooldown_hours", 4)
        last = self._cooldowns.get(phase, 0)
        return (time.time() - last) > (cooldown_hours * 3600)

    def _set_cooldown(self, phase: str):
        """Reset cooldown timer for a phase."""
        self._cooldowns[phase] = time.time()

    def _phase_state(self) -> dict:
        return {
            "absorb": self._absorb_enabled,
            "reflect": self._reflect_enabled,
            "explore": self._explore_enabled,
            "express": self._express_enabled,
            "memorize": self._memorize_enabled,
            "heartbeat": self._heartbeat_enabled,
            "custom_prompts": list(self._custom_prompts.keys()),
        }

    def _get_prompts(self) -> dict:
        """Return current prompts (defaults + custom overrides)."""
        defaults = {
            "absorb": "Default absorb",
            "reflect": "Default reflect",
            "explore": "Default explore",
            "express": "Default express",
            "memorize": "Default memorize",
        }
        defaults.update(self._custom_prompts)
        return defaults


def _disk_pct() -> int:
    """Return disk usage percentage."""
    try:
        result = subprocess.run(
            ["df", "--output=pcent", "/"], capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2:
            pct = lines[1].strip().rstrip("%")
            return int(pct) if pct.isdigit() else 0
    except Exception:
        pass
    return 0
