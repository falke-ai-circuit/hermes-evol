"""EVOL Stores — JSONL append-only state persistence."""

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

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
