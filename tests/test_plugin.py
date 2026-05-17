"""Tests for hermes-evol plugin tool dispatch layer.

CRITICAL: The 400 bug (invalid message content type: map[string]interface {})
occurred because EVOL tools returned raw Python dicts. Hermes v0.13.0 does NOT
auto-serialize tool results. This test suite enforces that every tool handler
returns a JSON string — never a dict — under all dispatch conditions.
"""

import json
import pytest

from hermes_evol.plugin import _wrap


# ── Test fixtures ──

def fake_engine_status(**kwargs):
    """Simulate engine.status() — returns a dict."""
    return {
        "engine": "hermes-evol",
        "version": "0.2.0",
        "heartbeat_alive": True,
        "state": "ACTIVE",
        "idle_seconds": 3600,
    }


def fake_engine_speak(**kwargs):
    """Simulate engine.speak(force=True) — returns a dict."""
    return {"phase": "express", "result": "Inner voice text"}


def fake_engine_reflect(**kwargs):
    """Simulate engine.reflect(force=True) — returns a dict."""
    return {
        "phase": "reflect",
        "patterns": {"patterns_found": 5},
        "llm_analysis": "Analysis text",
    }


def fake_string_handler(**kwargs):
    """A handler that already returns a string — should pass through."""
    return '{"result": "already json"}'


def fake_unwrapped_dict():
    """A handler taking zero args, returning a dict — simulate old broken code."""
    return {"engine": "hermes-evol", "state": "ACTIVE"}


# ── Core: _wrap must serialize dicts ──

class TestWrapSerialization:
    """The _wrap adapter MUST convert dict returns to JSON strings."""

    def test_wrap_converts_dict_to_json_string(self):
        """Dict return → JSON string. This is the 400 fix."""
        wrapped = _wrap(fake_engine_status)
        result = wrapped()
        assert isinstance(result, str), (
            f"BUG: _wrap returned {type(result).__name__}, not str. "
            f"This is the root cause of HTTP 400 'invalid message content type'."
        )
        parsed = json.loads(result)
        assert parsed["engine"] == "hermes-evol"

    def test_wrap_passes_through_string(self):
        """Already-string returns should pass through unchanged."""
        wrapped = _wrap(fake_string_handler)
        result = wrapped()
        assert isinstance(result, str)
        assert "already json" in result

    def test_wrap_zero_args_dict(self):
        """Handler with no args returning a dict — old broken code pattern."""
        wrapped = _wrap(fake_unwrapped_dict)
        result = wrapped()
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["state"] == "ACTIVE"


# ── Dispatch patterns: Hermes calls handlers different ways ──

class TestHermesDispatchPatterns:
    """Hermes dispatches as handler(args_dict, **kwargs) or handler()."""

    def test_positional_dict_arg(self):
        """Hermes dispatch: handler({"force": True}) — positional dict."""
        wrapped = _wrap(fake_engine_speak)
        result = wrapped({"force": True})
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["phase"] == "express"

    def test_named_kwargs(self):
        """Hermes may also dispatch as handler(force=True)."""
        wrapped = _wrap(fake_engine_speak)
        result = wrapped(force=True)
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["phase"] == "express"

    def test_no_args(self):
        """Hermes dispatch: handler() — no args."""
        wrapped = _wrap(fake_engine_status)
        result = wrapped()
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["state"] == "ACTIVE"

    def test_empty_dict_arg(self):
        """Hermes dispatch: handler({}) — empty positional dict."""
        wrapped = _wrap(fake_engine_status)
        result = wrapped({})
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["state"] == "ACTIVE"

    def test_dict_arg_plus_kwargs_merge(self):
        """If both args dict and kwargs are given, kwargs win."""
        wrapped = _wrap(fake_engine_speak)
        result = wrapped({"force": False}, force=True)
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["phase"] == "express"

    def test_multiple_positional_args_ignored_after_first(self):
        """Only first positional dict arg is used."""
        wrapped = _wrap(fake_engine_speak)
        result = wrapped({"force": True}, {"extra": "ignored"})
        assert isinstance(result, str)


# ── All EVOL tools must return JSON strings ──

class TestAllEvolToolsReturnJsonStrings:
    """Every registered EVOL tool MUST return a JSON string. No exceptions."""

    def test_all_tools_produce_valid_json(self):
        """Instantiate engine and verify every tool returns valid JSON string."""
        from hermes_evol.config import EvolConfig
        from hermes_evol.engine import EvolEngine

        config = EvolConfig()
        engine = EvolEngine(config)

        # Map of tool_name → (handler, test_args)
        tools = {
            "evol_status":  (_wrap(engine.status), {}),
            "evol_material": (_wrap(engine.material), {}),
            "evol_config":   (_wrap(engine.get_config), {}),
            "evol_speak":    (_wrap(engine.speak), {"force": True}),
            "evol_reflect":  (_wrap(engine.reflect), {"force": True}),
            "evol_explore":  (_wrap(engine.explore), {"query": "test"}),
            "evol_cycle":    (_wrap(engine.full_cycle), {"force": True}),
        }

        for name, (handler, args) in tools.items():
            # Test positional dict dispatch (Hermes standard)
            result = handler(args)
            assert isinstance(result, str), (
                f"{name}: handler(args) returned {type(result).__name__}, "
                f"not str. Content: {str(result)[:100]}"
            )
            # Must be valid JSON
            try:
                json.loads(result)
            except json.JSONDecodeError as e:
                pytest.fail(f"{name}: handler returned invalid JSON: {e}")

            # Test no-arg dispatch
            result2 = handler()
            assert isinstance(result2, str), (
                f"{name}: handler() returned {type(result2).__name__}"
            )
            try:
                json.loads(result2)
            except json.JSONDecodeError as e:
                pytest.fail(f"{name}: handler() returned invalid JSON: {e}")
