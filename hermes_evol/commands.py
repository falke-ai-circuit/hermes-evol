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

        if args in ("help", "h", "?"):
            ver = engine.cfg._version if hasattr(engine.cfg, '_version') else "0.5.2"
            return f"""🧬 EVOL — Subconscious Observer (v{ver})

5-phase cascade: absorb → reflect → express → explore → memorize

Commands:
help — Show this message
status — Heartbeat, cascade counters, cooldowns, phase readiness
material — Raw ingested data from absorb phase
config — Full config: phase models, hooks, search backends
phases — Per-phase enabled/disabled state

Trigger phases manually:
cycle — Run full 5-phase cascade (all, in order)
speak — Express phase: inner monologue + portrait/video hook
reflect — Analyze patterns and anomalies in absorbed data
explore — Search backends for discoveries from reflect patterns
memorize — Memory consolidation (manual=suggestion-only, shows proposals)

Review proposals (after memorize):
proposals — List pending proposals with IDs
proposals accept <id> — Apply a specific proposal
proposals reject <id> — Delete a specific proposal
proposals accept-all — Apply all pending proposals
proposals reject-all — Delete all pending proposals

Configure:
enable/disable <phase> — Toggle absorb, reflect, express, explore, memorize, heartbeat
memorize — Memory consolidation: score findings, weight adjustments, promotions (manual=suggestion-only)
prompt <phase> — Show prompt for a phase
prompt <phase> <text> — Override a phase prompt
log — Show current notification level
log off|low|high — off=silent, low=notifications, high=all+videos

⚙️ notify_level: {engine.cfg.notify_level}"""

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

        if args == "memorize":
            result = engine.memorize(force=True, manual=True)
            if isinstance(result, str):
                return result
            return json.dumps(result, indent=2, default=str)

        # ── Proposal review commands ──
        if parts[0] == "proposals":
            if len(parts) == 1:
                # List proposals
                return engine.list_proposals()
            action = parts[1]
            if action == "accept-all":
                return engine.accept_all_proposals()
            if action == "reject-all":
                return engine.reject_all_proposals()
            if action in ("accept", "reject") and len(parts) >= 3:
                prop_id = parts[2]
                if action == "accept":
                    return engine.accept_proposal(prop_id)
                return engine.reject_proposal(prop_id)
            return f"Usage: /evol proposals [accept|reject <id>|accept-all|reject-all]"

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

        if parts[0] == "log":
            levels = ["off", "low", "high"]
            if len(parts) < 2:
                return json.dumps({
                    "notify_level": engine.cfg.notify_level,
                    "available": levels,
                    "current": engine.cfg.notify_level,
                }, indent=2)
            level = parts[1].lower()
            return json.dumps(engine.set_notify_level(level), indent=2)

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
                "help", "status", "material", "config", "phases",
                "speak", "reflect", "explore", "cycle",
                "enable <phase>", "disable <phase>",
                "prompt <phase> [new text]",
                "log [off|low|high]",
            ],
        }, indent=2)

    return handler
