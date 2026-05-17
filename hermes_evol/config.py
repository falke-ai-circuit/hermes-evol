"""EVOL Config — schema, defaults, and environment loading."""

import os
from pathlib import Path


class EvolConfig:
    """Configuration container for the EVOL plugin."""

    def __init__(self, **kwargs):
        # Core
        self.heartbeat_interval: int = kwargs.get("heartbeat_interval", 900)
        self.state_file: str = kwargs.get(
            "state_file", "~/.hermes/workspace/circuit/state.jsonl"
        )
        self.material_file: str = kwargs.get(
            "material_file", "~/.hermes/workspace/circuit/material.jsonl"
        )
        self.voice_file: str = kwargs.get(
            "voice_file", "~/.hermes/workspace/circuit/voice.jsonl"
        )
        # Absorb
        self.absorb_sources = kwargs.get("absorb_sources", _default_sources())
        self.material_retention: int = kwargs.get("material_retention", 200)
        # Reflect
        self.reflect_backends = kwargs.get(
            "reflect_backends", _default_reflect_backends()
        )
        self.reflect_triggers = kwargs.get(
            "reflect_triggers", _default_reflect_triggers()
        )
        self.reflect_cooldown_hours: int = kwargs.get("reflect_cooldown_hours", 4)
        # Explore
        self.explore_backends = kwargs.get(
            "explore_backends", _default_explore_backends()
        )
        self.explore_triggers = kwargs.get(
            "explore_triggers", _default_explore_triggers()
        )
        self.explore_cooldown_hours: int = kwargs.get("explore_cooldown_hours", 6)
        self.explore_max_spawns_per_day: int = kwargs.get(
            "explore_max_spawns_per_day", 3
        )
        # Express
        self.express_outputs = kwargs.get(
            "express_outputs", _default_express_outputs()
        )
        self.express_triggers = kwargs.get(
            "express_triggers", _default_express_triggers()
        )
        self.express_cooldown_hours: int = kwargs.get("express_cooldown_hours", 12)
        # Memorize
        self.memorize_backends = kwargs.get(
            "memorize_backends", _default_memorize_backends()
        )
        self.memorize_triggers = kwargs.get(
            "memorize_triggers", _default_memorize_triggers()
        )
        self.memorize_cooldown_hours: int = kwargs.get("memorize_cooldown_hours", 0)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    @classmethod
    def from_env(cls):
        config_path = os.path.expanduser(
            os.environ.get(
                "EVOL_CONFIG_PATH", "~/.hermes/plugins/hermes-evol/config.yaml"
            )
        )
        kwargs = {}
        if os.path.exists(config_path):
            try:
                import yaml

                with open(config_path) as f:
                    cfg = yaml.safe_load(f) or {}
                _apply_yaml(cfg, kwargs)
            except Exception:
                pass

        # Environment overrides
        for key in [
            "heartbeat_interval",
            "reflect_cooldown_hours",
            "express_cooldown_hours",
            "explore_cooldown_hours",
        ]:
            env_key = f"EVOL_{key.upper()}"
            if env_key in os.environ:
                kwargs[key] = int(os.environ[env_key])
        return cls(**kwargs)


def _default_sources():
    return [
        {"name": "kanban"},
        {
            "name": "git",
            "repo": "~/.hermes",
            "files": ["SOUL.md", "AGENTS.md", "MEMORY.md"],
        },
        {"name": "sessions", "backend": "lcm", "profiles": ["conductor"]},
        {
            "name": "gateway",
            "log_path": "~/.hermes/profiles/conductor/logs/gateway.log",
            "patterns": ["OOM", "429", "stall", "crash", "sendMessage.*fail"],
        },
    ]


def _default_reflect_backends():
    return [{"name": "pattern_match"}, {"name": "local_llm", "thinking": "high"}]


def _default_reflect_triggers():
    return [
        {"name": "material_threshold", "min_entries": 5},
        {"name": "deep_rest", "min_idle_hours": 4},
    ]


def _default_explore_backends():
    return [
        {"name": "web_search", "provider": "integrated"},
        {
            "name": "knowledge_graph",
            "backend": "lightrag",
            "lightrag_url": "http://10.10.10.103:9622",
        },
    ]


def _default_explore_triggers():
    return [{"name": "reflect_gaps"}]


def _default_express_outputs():
    return [
        {
            "name": "falke_dna",
            "format": "video",
            "portrait_style": "chroma_glitch",
            "tts": "edge_tts",
        }
    ]


def _default_express_triggers():
    return [
        {"name": "reflect_complete"},
        {"name": "deep_rest", "min_idle_hours": 4},
    ]


def _default_memorize_backends():
    return [
        {"name": "lightrag", "url": "http://10.10.10.103:9622"},
        {"name": "memory_md", "promote_threshold": 0.50},
        {"name": "skills", "auto_create_threshold": 3},
        {"name": "circuit_edit", "mode": "suggest"},
    ]


def _default_memorize_triggers():
    return [{"name": "express_complete"}]


def _apply_yaml(cfg: dict, kwargs: dict):
    ec = cfg.get("evol", {})
    for key in ["heartbeat_interval", "state_file", "material_file", "voice_file"]:
        if key in ec:
            kwargs[key] = ec[key]

    sections = {
        "absorb": ("absorb_sources", "sources"),
        "reflect": ("reflect_backends", "backends"),
        "explore": ("explore_backends", "backends"),
        "express": ("express_outputs", "outputs"),
        "memorize": ("memorize_backends", "backends"),
    }
    for section, (kw_key, yk) in sections.items():
        if section in cfg:
            kwargs[kw_key] = cfg[section].get(yk, [])
            if section == "reflect":
                kwargs["reflect_triggers"] = cfg[section].get("triggers", [])
                kwargs["reflect_cooldown_hours"] = cfg[section].get(
                    "cooldown_hours", 4
                )
            elif section == "explore":
                kwargs["explore_triggers"] = cfg[section].get("triggers", [])
                kwargs["explore_cooldown_hours"] = cfg[section].get(
                    "cooldown_hours", 6
                )
            elif section == "express":
                kwargs["express_triggers"] = cfg[section].get("triggers", [])
                kwargs["express_cooldown_hours"] = cfg[section].get(
                    "voice_cooldown_hours", 12
                )
            elif section == "memorize":
                kwargs["memorize_triggers"] = cfg[section].get("triggers", [])
                kwargs["memorize_cooldown_hours"] = cfg[section].get(
                    "cooldown_hours", 0
                )
