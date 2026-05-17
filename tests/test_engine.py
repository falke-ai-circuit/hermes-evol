"""Tests for hermes-evol engine: heartbeat, state, phase orchestration."""

import json
import time
import pytest

from hermes_evol.config import EvolConfig
from hermes_evol.engine import EvolEngine
from hermes_evol.stores import StateStore, MaterialStore, VoiceStore


class TestStateStore:
    def test_append_and_read(self, tmp_path):
        path = tmp_path / "state.jsonl"
        store = StateStore(str(path))
        store.append({"ts": "2026-01-01T00:00:00Z", "state": "ACTIVE", "idle_sec": 0})
        store.append({"ts": "2026-01-01T00:15:00Z", "state": "RESTING", "idle_sec": 900})

        current = store.current()
        assert current is not None
        assert current["state"] == "RESTING"
        assert current["idle_sec"] == 900

    def test_empty_store_returns_none(self, tmp_path):
        path = tmp_path / "nonexistent.jsonl"
        store = StateStore(str(path))
        assert store.current() is None

    def test_large_file_reads_last_entry(self, tmp_path):
        path = tmp_path / "large.jsonl"
        store = StateStore(str(path))
        for i in range(100):
            store.append({"ts": f"entry-{i}", "state": "ACTIVE", "count": i})
        current = store.current()
        assert current["count"] == 99


class TestMaterialStore:
    def test_append_and_buffer(self, tmp_path):
        path = tmp_path / "material.jsonl"
        store = MaterialStore(str(path))
        store.append({"type": "kanban_completion", "title": "Task 1", "ts": "now"})
        assert len(store.buffer) == 1
        assert store.buffer[0]["type"] == "kanban_completion"

    def test_clear(self, tmp_path):
        path = tmp_path / "material.jsonl"
        store = MaterialStore(str(path))
        store.append({"type": "test", "value": 1})
        store.clear()
        assert len(store.buffer) == 0

    def test_gap_extraction(self, tmp_path):
        path = tmp_path / "material.jsonl"
        store = MaterialStore(str(path))
        store.set_reflection_result([
            {"patterns_found": 5, "name": "recurring_crash"},
            {"patterns_found": 10, "name": "memory_leak"},
            {"patterns_found": 2, "name": "minor"},
        ])
        gaps = store.get_gaps()
        assert len(gaps) == 2  # only patterns_found > 3

    def test_lessons_filter(self, tmp_path):
        path = tmp_path / "material.jsonl"
        store = MaterialStore(str(path))
        store.append({"type": "kanban_completion", "task_id": "T1"})
        store.append({"type": "gateway_anomaly", "pattern": "OOM"})
        store.append({"type": "session_checkpoint", "note": "ignored"})
        lessons = store.get_lessons()
        assert len(lessons) == 2
        lesson_types = {l["type"] for l in lessons}
        assert "kanban_completion" in lesson_types
        assert "gateway_anomaly" in lesson_types
        assert "session_checkpoint" not in lesson_types


class TestVoiceStore:
    def test_append_and_read(self, tmp_path):
        path = tmp_path / "voice.jsonl"
        store = VoiceStore(str(path))
        store.append({"ts": "2026-01-01", "monologue": "First voice", "mood": "dark"})
        store.append({"ts": "2026-01-02", "monologue": "Second voice", "mood": "hopeful"})

        last = store.last_voice()
        assert last["monologue"] == "Second voice"
        assert last["mood"] == "hopeful"

    def test_empty_returns_none(self, tmp_path):
        path = tmp_path / "nonexistent.jsonl"
        store = VoiceStore(str(path))
        assert store.last_voice() is None


class TestEvolEngine:
    def test_status_returns_dict(self):
        config = EvolConfig()
        engine = EvolEngine(config)
        status = engine.status()
        assert status["engine"] == "hermes-evol"
        assert "heartbeat_alive" in status
        assert "state" in status
        assert "infra" in status

    def test_material_returns_dict(self):
        config = EvolConfig()
        engine = EvolEngine(config)
        mat = engine.material()
        assert "entries" in mat
        assert "count" in mat

    def test_get_config_returns_dict(self):
        config = EvolConfig()
        engine = EvolEngine(config)
        cfg = engine.get_config()
        assert "heartbeat_interval" in cfg
        assert "phase_state" in cfg

    def test_reflect_without_cooldown(self):
        """Reflect should work when forced."""
        config = EvolConfig()
        engine = EvolEngine(config)
        result = engine.reflect(force=True)
        assert result["phase"] == "reflect"
        assert "patterns" in result

    def test_speak_without_cooldown(self):
        """Speak should work when forced."""
        config = EvolConfig()
        engine = EvolEngine(config)
        result = engine.speak(force=True)
        assert result["phase"] == "express"

    def test_explore_without_cooldown(self):
        config = EvolConfig()
        engine = EvolEngine(config)
        result = engine.explore(force=True)
        assert result["phase"] == "explore_llm"

    def test_full_cycle(self):
        config = EvolConfig()
        engine = EvolEngine(config)
        result = engine.full_cycle(force=True)
        assert result["phase"] == "full_cycle"
        assert "outputs" in result
        assert "reflect" in result["outputs"]

    def test_phase_state(self):
        config = EvolConfig()
        engine = EvolEngine(config)
        state = engine._phase_state()
        assert state["absorb"] is True
        assert state["reflect"] is True
        assert state["express"] is True

    def test_start_stop(self):
        config = EvolConfig(heartbeat_interval=60)
        engine = EvolEngine(config)
        engine.start()
        assert engine._running is True
        assert engine._thread is not None
        engine.stop()
        assert engine._running is False

    def test_cooldown_blocks_unforced(self):
        config = EvolConfig(reflect_cooldown_hours=999)
        engine = EvolEngine(config)
        engine._set_cooldown("reflect")
        result = engine.reflect(force=False)
        assert result.get("blocked") == "cooldown"

    def test_disabled_phase_blocks(self):
        config = EvolConfig()
        engine = EvolEngine(config)
        engine._express_enabled = False
        result = engine.speak(force=True)
        assert result.get("blocked") == "disabled"
