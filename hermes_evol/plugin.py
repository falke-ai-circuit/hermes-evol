"""Hermes Agent plugin entry point for hermes-evol.

This is the bridge between the hermes_evol package and the Hermes Agent
plugin system. It handles tool registration with proper JSON serialization
so that all tool outputs are strings — never raw Python dicts.

CRITICAL: Raw dicts in tool message content cause HTTP 400
"invalid message content type: map[string]interface {}"
on strict OpenAI-compatible providers (Ollama Cloud, etc.).

Hermes v0.13.0 dispatches tool handlers as handler(args_dict, **kwargs)
where args_dict is a positional dict. Engine methods accept **kwargs.
The _wrap adapter bridges both patterns AND ensures JSON string output.
"""

import json as _json
import logging as _logging
import sys as _sys
import os as _os

_logger = _logging.getLogger(__name__)


def _build_schema(params: dict | None = None, required: list | None = None) -> dict:
    """Build a minimal OpenAI-style tool schema."""
    return {
        "type": "function",
        "function": {
            "name": "",
            "parameters": {
                "type": "object",
                "properties": params or {},
                "required": required or [],
            },
        },
    }


def _wrap(fn):
    """Wrap an engine method so it always returns a JSON string.

    Hermes dispatches tool handlers as handler(args_dict, **kwargs)
    where args_dict is a positional dict of parsed tool arguments.
    Engine methods expect named **kwargs. We bridge both patterns.

    ALL EVOL tools MUST go through this wrapper. No exceptions.
    The test suite enforces this: test_all_tools_return_json_strings.
    """
    def _wrapped(*args, **kwargs):
        # Hermes dispatch: handler({"force": True}) — positional dict
        if args and isinstance(args[0], dict) and not kwargs:
            kwargs = args[0]
        # Hermes injects task_id and other internal kwargs — filter them out
        kwargs = {k: v for k, v in kwargs.items() if k not in ('task_id', 'session_id', 'actor_id')}
        result = fn(**kwargs) if kwargs else fn()
        if isinstance(result, str):
            return result
        return _json.dumps(result, indent=2, default=str)

    return _wrapped


def register(ctx):
    """Plugin entry point — called by Hermes at gateway startup.

    Registers all EVOL tools with proper JSON string serialization.
    Starts the background heartbeat. Registers the /evol slash command.
    """
    from hermes_evol.config import EvolConfig
    from hermes_evol.engine import EvolEngine
    from hermes_evol.commands import build_command_handler

    _logger.info("hermes-evol v0.2.0 registering...")

    config = EvolConfig.from_env()
    engine = EvolEngine(config)

    # ── Register tools ──
    # Every handler goes through _wrap() to guarantee JSON string output.
    # The wrapper:
    #   1. Accepts positional dict args (Hermes dispatch pattern)
    #   2. Converts engine method dict → json.dumps string
    #   3. Passes through already-string results unchanged

    ctx.register_tool(
        "evol_status", "evol", _build_schema(),
        _wrap(engine.status),
        description="Get EVOL observer status (heartbeat, phases, material counts)",
        emoji="🧠",
    )

    ctx.register_tool(
        "evol_material", "evol", _build_schema(),
        _wrap(engine.material),
        description="View accumulated material from absorb phase",
        emoji="📥",
    )

    ctx.register_tool(
        "evol_config", "evol", _build_schema(),
        _wrap(engine.get_config),
        description="Show current EVOL configuration",
        emoji="⚙️",
    )

    ctx.register_tool(
        "evol_speak", "evol",
        _build_schema(
            params={
                "force": {
                    "type": "boolean",
                    "description": "Force inner voice expression regardless of cooldown",
                }
            },
            required=[],
        ),
        _wrap(engine.speak),
        description="Trigger EVOL inner voice expression (monologue + portrait)",
        emoji="🗣️",
    )

    ctx.register_tool(
        "evol_reflect", "evol",
        _build_schema(
            params={
                "force": {
                    "type": "boolean",
                    "description": "Force reflection regardless of trigger threshold",
                }
            },
            required=[],
        ),
        _wrap(engine.reflect),
        description="Trigger EVOL reflection on accumulated patterns",
        emoji="🪞",
    )

    ctx.register_tool(
        "evol_explore", "evol",
        _build_schema(
            params={
                "query": {"type": "string", "description": "Optional topic to explore"},
                "force": {
                    "type": "boolean",
                    "description": "Force exploration regardless of cooldown",
                },
            },
            required=[],
        ),
        _wrap(engine.explore),
        description="Trigger EVOL knowledge exploration",
        emoji="🔍",
    )

    ctx.register_tool(
        "evol_cycle", "evol",
        _build_schema(
            params={
                "force": {
                    "type": "boolean",
                    "description": "Force full cycle execution",
                }
            },
            required=[],
        ),
        _wrap(engine.full_cycle),
        description="Run a complete EVOL cycle",
        emoji="🔄",
    )

    # ── Register slash command ──
    ctx.register_command(
        "evol",
        build_command_handler(engine),
        description="EVOL — subconscious observer status and control",
    )

    # ── Start background heartbeat ──
    try:
        engine.start()
    except Exception:
        _logger.exception("EVOL heartbeat start failed")

    _logger.info("hermes-evol v0.2.0 loaded — subconscious observer active")
