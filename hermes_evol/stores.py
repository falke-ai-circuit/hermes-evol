"""EVOL Stores — JSONL append-only state persistence."""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional, Dict

logger = logging.getLogger(__name__)


class StateStore:
    """Append-only state.jsonl — organism vitals every heartbeat."""

    def __init__(self, path: str):
        self.path = Path(os.path.expanduser(path))
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: dict):
        """Append a state line."""
        try:
            with open(self.path, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception:
            logger.exception("StateStore append failed")

    def current(self) -> Optional[dict]:
        """Return the most recent state entry."""
        if not self.path.exists():
            return None
        try:
            with open(self.path, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                if size < 2:
                    return None
                f.seek(max(0, size - 2048))
                tail = f.read().decode("utf-8", errors="replace")
                lines = tail.strip().split("\n")
                return json.loads(lines[-1]) if lines else None
        except Exception:
            return None


class MaterialStore:
    """Append-only material.jsonl — accumulated events between voices."""

    def __init__(self, path: str):
        self.path = Path(os.path.expanduser(path))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.buffer: list[dict] = []
        self._gaps: list[str] = []
        self._lessons: list[dict] = []
        self._reflections: list[dict] = []
        self._load()

    def _load(self):
        """Load buffer from disk on startup."""
        if not self.path.exists():
            return
        try:
            with open(self.path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self.buffer.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass

    def append(self, entry: dict):
        """Append one entry to buffer + disk."""
        self.buffer.append(entry)
        try:
            with open(self.path, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception:
            logger.exception("MaterialStore append failed")

    def clear(self):
        """Clear buffer and truncate disk file."""
        self.buffer.clear()
        self._gaps.clear()
        self._lessons.clear()
        self._reflections.clear()
        try:
            self.path.write_text("")
        except Exception:
            pass

    def set_reflection_result(self, findings: list[dict]):
        """Store reflection output. Extract gaps."""
        self._reflections = findings
        for f in findings:
            if isinstance(f, dict) and f.get("patterns_found", 0) > 3:
                self._gaps.append(
                    f"Unusual pattern count: {f.get('patterns_found')}"
                )

    def get_gaps(self) -> list[str]:
        """Return unanswered questions from reflection."""
        return self._gaps

    def get_lessons(self) -> list[dict]:
        """Return learnable items from buffer."""
        return [
            {"type": e.get("type"), "content": e}
            for e in self.buffer[-20:]
            if e.get("type")
            in ("kanban_completion", "circuit_edit", "gateway_anomaly")
        ]

    def since_last_voice(self) -> list[dict]:
        """Return all entries accumulated since last clear."""
        return self.buffer


class VoiceStore:
    """Append-only voice.jsonl — when inner voice spoke."""

    def __init__(self, path: str):
        self.path = Path(os.path.expanduser(path))
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: dict):
        """Record a voice expression."""
        try:
            with open(self.path, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception:
            logger.exception("VoiceStore append failed")

    def last_voice(self) -> Optional[dict]:
        """Return the most recent voice entry."""
        if not self.path.exists():
            return None
        try:
            with open(self.path, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                if size < 2:
                    return None
                f.seek(max(0, size - 2048))
                tail = f.read().decode("utf-8", errors="replace")
                lines = tail.strip().split("\n")
                return json.loads(lines[-1]) if lines else None
        except Exception:
            return None


# ═══════════════════════════════════════════════════════════════════
# AGENT SESSION TRACKER — Per-agent EVOL v2 (event-driven)
# ═══════════════════════════════════════════════════════════════════

class AgentSessionTracker:
    """Tracks per-agent session activity for threshold-based EVOL triggers.

    Records tool call count + token count per agent session.
    Writes to ~/.hermes/profiles/{agent}/evol-session-tracker.jsonl

    Trigger condition (completion-count based, file-backed):
        completions >= per_agent_min_completions (default 5) since last cycle
        (each task_end call = one completion, tracked in JSONL)
    """

    def __init__(self, profiles_dir: str = None):
        base = profiles_dir or os.path.expanduser("~/.hermes/profiles")
        self._profiles_dir = Path(base)
        self._active_sessions: Dict[str, dict] = {}  # agent_profile -> current session stats

    def _tracker_path(self, agent_profile: str) -> Path:
        return self._profiles_dir / agent_profile / "evol-session-tracker.jsonl"

    def _per_agent_cooldown_path(self, agent_profile: str) -> Path:
        return self._profiles_dir / agent_profile / "evol" / ".last_per_agent_cycle"

    def _global_fallback_path(self) -> Path:
        base = os.environ.get("HERMES_CONFIG_DIR", str(Path.home() / ".hermes"))
        return Path(base) / "workspace" / "circuit" / ".last_any_evol"

    def start_session(self, agent_profile: str, session_id: str = ""):
        """Initialize tracking for a new agent session."""
        self._active_sessions[agent_profile] = {
            "session_id": session_id or f"session-{int(time.time())}",
            "tool_calls": 0,
            "total_tokens": 0,
            "started_at": time.time(),
        }

    def record_tool_call(self, agent_profile: str, tokens_used: int = 0):
        """Record a tool call during an agent session."""
        if agent_profile not in self._active_sessions:
            self.start_session(agent_profile)
        sess = self._active_sessions[agent_profile]
        sess["tool_calls"] += 1
        sess["total_tokens"] += tokens_used

    def check_threshold(
        self,
        agent_profile: str,
        min_completions: int = 5,
        cooldown_hours: int = 4,
    ) -> bool:
        """Check if per-agent EVOL should fire.

        Reads the JSONL tracker file to count completions since last EVOL cycle.
        Returns True if: completions >= min_completions
        AND cooldown period has passed since last per-agent cycle.

        This is file-backed — survives tracker instance lifetime.
        """
        tracker_path = self._tracker_path(agent_profile)
        if not tracker_path.exists():
            return False

        # Read all entries, count completions since last EVOL cycle
        cooldown_path = self._per_agent_cooldown_path(agent_profile)
        since_ts = 0.0
        if cooldown_path.exists():
            try:
                since_ts = float(cooldown_path.read_text().strip())
            except (ValueError, OSError):
                pass

        completion_count = 0
        try:
            for line in tracker_path.read_text().strip().splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    entry_ts = entry.get("ended_at", 0)
                    if entry_ts > since_ts:
                        completion_count += 1
                except json.JSONDecodeError:
                    pass
        except OSError:
            return False

        if completion_count < min_completions:
            return False

        # Check cooldown
        if since_ts > 0:
            elapsed_hours = (time.time() - since_ts) / 3600
            if elapsed_hours < cooldown_hours:
                return False

        return True

    def check_global_fallback(
        self,
        idle_seconds: float,
        fallback_hours: int = 24,
        min_idle_hours: float = 2.0,
    ) -> bool:
        """Check if global idle fallback should fire.

        Returns True if: no per-agent EVOL in fallback_hours AND Goran idle > min_idle_hours.
        """
        # Check global last-any-evol marker
        marker = self._global_fallback_path()
        if marker.exists():
            try:
                last_evol_ts = float(marker.read_text().strip())
                hours_since_last_evol = (time.time() - last_evol_ts) / 3600
                if hours_since_last_evol < fallback_hours:
                    return False
            except (ValueError, OSError):
                pass

        # Check idle threshold
        idle_hours = idle_seconds / 3600
        return idle_hours > min_idle_hours

    def touch_per_agent_cycle(self, agent_profile: str):
        """Record that a per-agent EVOL cycle completed."""
        cooldown_path = self._per_agent_cooldown_path(agent_profile)
        cooldown_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            cooldown_path.write_text(str(time.time()))
        except OSError:
            pass

        # Also update global marker
        marker = self._global_fallback_path()
        marker.parent.mkdir(parents=True, exist_ok=True)
        try:
            marker.write_text(str(time.time()))
        except OSError:
            pass

        # Reset session tracker
        if agent_profile in self._active_sessions:
            del self._active_sessions[agent_profile]

    def end_session(self, agent_profile: str) -> Optional[dict]:
        """End tracking and write session stats to JSONL. Returns session dict or None."""
        if agent_profile not in self._active_sessions:
            return None

        sess = self._active_sessions.pop(agent_profile)
        sess["ended_at"] = time.time()
        sess["duration_seconds"] = round(sess["ended_at"] - sess["started_at"], 2)

        # Write to tracker JSONL
        tracker_path = self._tracker_path(agent_profile)
        tracker_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(tracker_path, "a") as f:
                f.write(json.dumps(sess, default=str) + "\n")
        except Exception:
            logger.exception("AgentSessionTracker write failed for %s", agent_profile)

        return sess

    def recent_sessions(self, agent_profile: str, limit: int = 5) -> list[dict]:
        """Return recent session entries for an agent."""
        tracker_path = self._tracker_path(agent_profile)
        if not tracker_path.exists():
            return []
        entries = []
        try:
            lines = tracker_path.read_text().strip().splitlines()
            for line in lines[-limit:]:
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        except OSError:
            pass
        return entries
