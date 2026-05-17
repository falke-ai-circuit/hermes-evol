"""EVOL Commands — /evol slash command handler."""

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import EvolEngine


def build_command_handler(engine: "EvolEngine"):
    """Return a handler function for /evol slash commands."""

    def handler(raw_args: str) -> str:
        args = raw_args.strip().lower() if raw_args else ""
        parts = args.split(maxsplit=1)

        if args in ("status", "", None):
            return json.dumps(engine.status(), indent=2, default=str)

        if args == "material":
            return json.dumps(engine.material(), indent=2, default=str)

        if args == "config":
            return json.dumps(engine.get_config(), indent=2, default=str)

        if args == "speak":
            return json.dumps(engine.speak(force=True), indent=2, default=str)

        if args == "reflect":
            return json.dumps(engine.reflect(force=True), indent=2, default=str)

        if args == "explore":
            return json.dumps(engine.explore(force=True), indent=2, default=str)

        if args == "cycle":
            return json.dumps(engine.full_cycle(force=True), indent=2, default=str)

        if parts[0] in ("enable", "disable"):
            action = parts[0]
            if len(parts) < 2:
                return json.dumps({
                    "error": f"Usage: /evol {action} <phase>",
                    "phases": [
                        "absorb", "reflect", "explore", "express",
                        "memorize", "heartbeat",
                    ],
                })
            phase = parts[1]
            valid = ["absorb", "reflect", "explore", "express", "memorize", "heartbeat"]
            if phase not in valid:
                return json.dumps({"error": f"Unknown phase: {phase}", "valid": valid})
            setattr(engine, f"_{phase}_enabled", action == "enable")
            return json.dumps({
                "phase": phase,
                "enabled": action == "enable",
                "state": engine._phase_state(),
            })

        if parts[0] == "prompt":
            if len(parts) < 2:
                return json.dumps({"prompts": engine._get_prompts()}, indent=2, default=str)
            sub = parts[1].split(maxsplit=1)
            phase = sub[0]
            new_text = sub[1] if len(sub) > 1 else ""
            valid = ["absorb", "reflect", "explore", "express", "memorize"]
            if phase not in valid:
                return json.dumps({"error": f"Unknown phase: {phase}", "valid": valid})
            if not new_text:
                return json.dumps({
                    "phase": phase,
                    "current_prompt": engine._get_prompts().get(phase, "default"),
                })
            engine._custom_prompts[phase] = new_text
            return json.dumps({"phase": phase, "prompt_updated": True, "length": len(new_text)})

        if args == "phases":
            return json.dumps(engine._phase_state(), indent=2)

        return json.dumps({
            "error": f"Unknown /evol command: {args}",
            "available": [
                "status", "material", "config", "phases",
                "speak", "reflect", "explore", "cycle",
                "enable <phase>", "disable <phase>",
                "prompt <phase> [new text]",
            ],
        }, indent=2)

    return handler
