"""
EVOL Configuration — Universal, Profile-Aware, Hermes-Integrated.

Per-phase model control, edit modes, circuit-aware weights.
Supports "profile" mode (one EVOL per profile, scoped to own data)
and "global" mode (one EVOL across all profiles, unified cycle).

Config file: <profile_dir>/evol.json  (auto-created with defaults)
Env overrides: EVOL_MODE, EVOL_ENABLED, EVOL_EDIT_MODE,
               EVOL_<PHASE>_MODEL, EVOL_<PHASE>_PROVIDER, EVOL_<PHASE>_API_KEY
"""

import json
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Literal, Any


# ── Per-phase model configuration ──────────────────────────────────

@dataclass
class PhaseModelConfig:
    """Model configuration for a single EVOL phase."""
    provider: str = ""       # e.g. "ollama", "venice", "openai", "" = Hermes default
    model: str = ""          # e.g. "deepseek-v4-pro", "" = use provider default
    api_key: str = ""        # override API key, "" = use Hermes env
    temperature: float = 0.7
    max_tokens: int = 4096

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "api_key": self.api_key,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PhaseModelConfig":
        return cls(
            provider=d.get("provider", ""),
            model=d.get("model", ""),
            api_key=d.get("api_key", ""),
            temperature=d.get("temperature", 0.7),
            max_tokens=d.get("max_tokens", 4096),
        )

    @property
    def is_configured(self) -> bool:
        """True if user explicitly set a model or provider."""
        return bool(self.provider or self.model)


# ── Circuit file weight configuration ──────────────────────────────

@dataclass
class CircuitWeight:
    """Weight for a circuit file — determines MEMORIZE promotion threshold."""
    path: str           # relative to profile dir: "SOUL.md", "AGENTS.md", etc.
    weight: float       # 0.0-1.0 base weight multiplier
    role: str           # "identity", "behavior", "knowledge", "memory"

# Default circuit weights per profile type (used when no profile-specific config)
DEFAULT_CIRCUIT_WEIGHTS: Dict[str, List[CircuitWeight]] = {
    # Conductor = orchestrator profile — identity + behavior critical
    "conductor": [
        CircuitWeight("SOUL.md", 1.00, "identity"),
        CircuitWeight("AGENTS.md", 0.95, "behavior"),
        CircuitWeight("MEMORY.md", 0.65, "knowledge"),
        CircuitWeight("IDENTITY.md", 0.90, "identity"),
    ],
    # Worker profiles — behavior + knowledge critical
    "default": [
        CircuitWeight("SOUL.md", 0.90, "identity"),
        CircuitWeight("AGENTS.md", 0.85, "behavior"),
        CircuitWeight("MEMORY.md", 0.80, "knowledge"),
        CircuitWeight("SKILL.md", 0.70, "knowledge"),
    ],
    # Shadow = dark exploration — identity critical, behavior loose
    "shadow": [
        CircuitWeight("SOUL.md", 0.95, "identity"),
        CircuitWeight("AGENTS.md", 0.60, "behavior"),
        CircuitWeight("MEMORY.md", 0.75, "knowledge"),
    ],
}

# Fallback: files every profile has
UNIVERSAL_CIRCUIT_FILES = ["SOUL.md", "AGENTS.md", "MEMORY.md", "IDENTITY.md"]


# ── Provider → Endpoint mapping (universal, portable) ──────────────
# EVOL calls these APIs directly — no Hermes gateway needed.
# Extendable: add any OpenAI-compatible provider.
PROVIDER_ENDPOINTS: Dict[str, dict] = {
    "ollama-cloud": {
        "base_url": "https://ollama.com/v1",
        "api_key_env": "OLLAMA_API_KEY",
        "description": "Ollama Cloud — fast OpenAI-compatible API",
    },
    "venice": {
        "base_url": "https://api.venice.ai/api/v1",
        "api_key_env": "VENICE_API_KEY",
        "description": "Venice AI — uncensored models, E2EE",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "description": "OpenRouter — model aggregator",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "api_key_env": "ANTHROPIC_API_KEY",
        "description": "Anthropic — Claude models (uses messages API)",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "description": "OpenAI — GPT models",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "description": "DeepSeek official API",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "description": "Groq — fast inference",
    },
    "custom": {
        "base_url": "",
        "api_key_env": "",
        "description": "Custom OpenAI-compatible endpoint — set via search_backend_url + search_api_key or env vars",
    },
}

# ── Voice & Portrait config (modular, not Falke-hardcoded) ─────────

@dataclass
class VoiceConfig:
    """Voice synthesis configuration for EXPRESS output."""
    enabled: bool = False                      # whether to generate voice
    provider: Literal["none", "elevenlabs", "edge", "openai", "custom"] = "none"
    elevenlabs_voice_id: str = ""              # e.g. "pNInz6obpgDQGcFmaJgB" (Adam)
    elevenlabs_model: str = "eleven_multilingual_v2"
    edge_voice: str = "en-US-AriaNeural"       # Free, built into Windows/Hermes
    openai_voice: str = "alloy"
    custom_command: str = ""                   # shell command that takes text→audio file
    output_dir: str = ""                       # where to save audio, default: evol/voice/

@dataclass
class PortraitConfig:
    """Portrait/image generation configuration for EXPRESS output."""
    enabled: bool = False                      # whether to generate portrait
    provider: Literal["none", "chroma", "comfyui", "openai", "custom"] = "none"
    chroma_colors: str = "dark cyberpunk purple cyan black"  # color palette
    comfyui_workflow: str = ""                 # path to workflow JSON
    openai_model: str = "dall-e-3"
    custom_command: str = ""                   # shell command: prompt→image
    output_dir: str = ""                       # default: evol/portraits/


# ── Main Config ────────────────────────────────────────────────────

@dataclass
class EvolConfig:
    """
    Universal EVOL configuration.

    Load order (last wins):
      1. Hardcoded defaults
      2. <profile_dir>/evol.json
      3. Environment variables (EVOL_*)
    """

    # ── Global ──
    mode: Literal["profile", "global"] = "profile"
    enabled: bool = True
    edit_mode: Literal["auto", "suggested", "readonly"] = "suggested"
    profile: str = "conductor"
    profile_dir: str = ""
    profiles_dir: str = ""

    # ── Phase toggles ──
    phase_enabled: Dict[str, bool] = field(default_factory=lambda: {
        "absorb": True,
        "reflect": True,
        "explore": True,
        "express": True,
        "memorize": True,
    })

    # ── Per-phase model configs ──
    phase_models: Dict[str, PhaseModelConfig] = field(default_factory=lambda: {
        "absorb": PhaseModelConfig(temperature=0.3, max_tokens=4096),
        "reflect": PhaseModelConfig(temperature=0.5, max_tokens=8192),
        "explore": PhaseModelConfig(temperature=0.7, max_tokens=4096),
        "express": PhaseModelConfig(temperature=0.9, max_tokens=4096),
        "memorize": PhaseModelConfig(temperature=0.3, max_tokens=4096),
    })

    # ── Circuit weights ──
    circuit_weights: List[CircuitWeight] = field(default_factory=list)

    # ── Sources ──
    sources: Dict[str, dict] = field(default_factory=dict)

    # ── Timing ──
    cooldown_minutes: int = 240          # minimum between cycles
    express_cooldown_hours: int = 12     # minimum between express outputs
    idle_trigger_minutes: int = 30       # idle time before trigger
    activity_trigger_tasks: int = 1      # completed tasks before activity trigger

    # ── Global mode ──
    global_profiles: List[str] = field(default_factory=list)  # profiles to scan

    # ── Search backends (configured per-instance via evol.json) ──
    search_backend: Literal["duckduckgo", "wikipedia", "searxng", "firecrawl", "google"] = "wikipedia"
    search_backend_url: str = ""    # SearXNG URL, Google CSE endpoint, etc.
    search_api_key: str = ""        # API key for firecrawl/google
    search_backends: List[Dict[str, str]] = field(default_factory=list)  # multi-backend: [{name, url, key}]

    # ── Limits ──
    max_retries_per_phase: int = 3
    max_cycles_per_day: int = 6

    def __init__(self, profile: Optional[str] = None, mode: Optional[str] = None):
        """Initialize EVOL config for a profile."""
        # ── Set dataclass defaults (custom __init__ must do this explicitly) ──
        self.mode = "profile"
        self.enabled = True
        self.edit_mode = "auto"
        self.phase_enabled = {
            "absorb": True, "reflect": True, "explore": True,
            "express": True, "memorize": True,
        }
        self.phase_models = {
            "absorb": PhaseModelConfig(temperature=0.3, max_tokens=4096),
            "reflect": PhaseModelConfig(temperature=0.5, max_tokens=8192),
            "explore": PhaseModelConfig(temperature=0.7, max_tokens=4096),
            "express": PhaseModelConfig(temperature=0.9, max_tokens=4096),
            "memorize": PhaseModelConfig(temperature=0.3, max_tokens=4096),
        }
        self.circuit_weights = []
        self.sources = {}
        self.cooldown_minutes = 240
        self.express_cooldown_hours = 12
        self.idle_trigger_minutes = 30
        self.activity_trigger_tasks = 1
        self.global_profiles = []
        self.search_backend = "wikipedia"
        self.search_backend_url = ""
        self.search_api_key = ""
        self.search_backends = []
        self.max_retries_per_phase = 3
        self.max_cycles_per_day = 6
        self.profile_dir = ""
        self.profiles_dir = ""
        self.voice_config = VoiceConfig()
        self.portrait_config = PortraitConfig()
        self._provider_base_url: Dict[str, str] = {}  # resolved endpoints

        # Detect profile
        self.profile = profile or self._detect_profile()

        # Resolve paths
        base = Path(os.environ.get("HERMES_CONFIG_DIR", Path.home() / ".hermes"))
        self.profiles_dir = str(base / "profiles")
        self.profile_dir = str(base / "profiles" / self.profile)

        # Read Hermes config for default model/provider
        self._detect_default_provider()

        # Load from file
        self._load_from_file()

        # Apply env overrides
        self._apply_env_overrides()

        # Override mode if explicitly passed
        if mode:
            self.mode = mode  # type: ignore

        # Build sources (profile-aware)
        self._build_sources()

        # Load circuit weights (profile-aware)
        self._load_circuit_weights()

    # ── Detection ────────────────────────────────────────────────

    def _detect_profile(self) -> str:
        """Detect active profile from environment or config files."""
        env = os.environ.get("HERMES_PROFILE", "")
        if env:
            return env.strip()

        for candidate in [
            Path(os.environ.get("HERMES_CONFIG_DIR", Path.home() / ".hermes")) / "active_profile",
            Path.home() / ".hermes" / "active_profile",
        ]:
            if candidate.exists():
                val = candidate.read_text().strip()
                if val:
                    return val
        return "conductor"

    def _detect_default_provider(self):
        """Read Hermes config.yaml for default model/provider, resolve API endpoints.
        Uses PROVIDER_ENDPOINTS mapping for direct API calls — no gateway needed."""
        # Try profile-specific config first, then global
        config_paths = [
            Path(self.profile_dir) / "config.yaml",
            Path(self.profiles_dir).parent / "config.yaml",
        ]
        hermes_cfg = {}
        for cp in config_paths:
            if cp.exists():
                try:
                    import yaml
                    hermes_cfg = yaml.safe_load(cp.read_text()) or {}
                    break
                except Exception:
                    pass

        model_section = hermes_cfg.get("model", {})
        provider = model_section.get("provider", "ollama-cloud")
        model = model_section.get("default", "deepseek-v4-pro")

        # Resolve endpoint
        endpoint = PROVIDER_ENDPOINTS.get(provider)
        if not endpoint:
            endpoint = PROVIDER_ENDPOINTS["ollama-cloud"]
            provider = "ollama-cloud"

        self._provider_base_url[provider] = endpoint["base_url"]

        # Set defaults on unconfigured phase models
        for phase in self.phase_models:
            pm = self.phase_models[phase]
            if not pm.provider:
                pm.provider = provider
            if not pm.model:
                pm.model = model

    def _load_from_file(self):
        """Load configuration from evol.json in the profile directory."""
        config_path = Path(self.profile_dir) / "evol.json"

        if not config_path.exists():
            # Auto-create with defaults
            self._save_to_file()
            return

        try:
            data = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            return

        # Top-level config
        if "mode" in data:
            self.mode = data["mode"]
        if "enabled" in data:
            self.enabled = data["enabled"]
        if "edit_mode" in data:
            self.edit_mode = data["edit_mode"]
        if "cooldown_minutes" in data:
            self.cooldown_minutes = data["cooldown_minutes"]
        if "express_cooldown_hours" in data:
            self.express_cooldown_hours = data["express_cooldown_hours"]
        if "idle_trigger_minutes" in data:
            self.idle_trigger_minutes = data["idle_trigger_minutes"]
        if "activity_trigger_tasks" in data:
            self.activity_trigger_tasks = data["activity_trigger_tasks"]
        if "max_retries_per_phase" in data:
            self.max_retries_per_phase = data["max_retries_per_phase"]
        if "max_cycles_per_day" in data:
            self.max_cycles_per_day = data["max_cycles_per_day"]

        # Phase toggles
        if "phases" in data:
            for phase, enabled in data["phases"].items():
                if phase in self.phase_enabled:
                    self.phase_enabled[phase] = enabled

        # Phase models
        if "phase_models" in data:
            for phase, model_data in data["phase_models"].items():
                if phase in self.phase_models:
                    self.phase_models[phase] = PhaseModelConfig.from_dict(model_data)

        # Global profiles
        if "global_profiles" in data:
            self.global_profiles = data["global_profiles"]

        # Search backend
        if "search_backend" in data:
            self.search_backend = data["search_backend"]
        if "search_backend_url" in data:
            self.search_backend_url = data["search_backend_url"]
        if "search_api_key" in data:
            self.search_api_key = data["search_api_key"]

        # Circuit weights (custom overrides)
        if "circuit_weights" in data:
            self.circuit_weights = [
                CircuitWeight(**w) for w in data["circuit_weights"]
            ]

    def _save_to_file(self):
        """Save current config to evol.json."""
        config_path = Path(self.profile_dir) / "evol.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        config_path.write_text(json.dumps(data, indent=2))

    def _apply_env_overrides(self):
        """Apply environment variable overrides (EVOL_*)."""
        env_map = {
            "EVOL_MODE": "mode",
            "EVOL_ENABLED": "enabled",
            "EVOL_EDIT_MODE": "edit_mode",
            "EVOL_COOLDOWN_MINUTES": "cooldown_minutes",
            "EVOL_EXPRESS_COOLDOWN_HOURS": "express_cooldown_hours",
            "EVOL_IDLE_TRIGGER_MINUTES": "idle_trigger_minutes",
            "EVOL_ACTIVITY_TRIGGER_TASKS": "activity_trigger_tasks",
        }

        for env_var, attr in env_map.items():
            val = os.environ.get(env_var, "")
            if not val:
                continue
            if attr == "enabled":
                self.enabled = val.lower() in ("1", "true", "yes")
            elif attr == "edit_mode":
                if val in ("auto", "suggested", "readonly"):
                    self.edit_mode = val  # type: ignore
            elif attr == "mode":
                if val in ("profile", "global"):
                    self.mode = val  # type: ignore
            else:
                try:
                    setattr(self, attr, int(val))
                except ValueError:
                    pass

        # Per-phase model overrides: EVOL_<PHASE>_MODEL, EVOL_<PHASE>_PROVIDER, EVOL_<PHASE>_API_KEY
        for phase in self.phase_models:
            pm = self.phase_models[phase]
            phase_upper = phase.upper()
            if os.environ.get(f"EVOL_{phase_upper}_MODEL"):
                pm.model = os.environ[f"EVOL_{phase_upper}_MODEL"]
            if os.environ.get(f"EVOL_{phase_upper}_PROVIDER"):
                pm.provider = os.environ[f"EVOL_{phase_upper}_PROVIDER"]
            if os.environ.get(f"EVOL_{phase_upper}_API_KEY"):
                pm.api_key = os.environ[f"EVOL_{phase_upper}_API_KEY"]

    def _build_sources(self):
        """Build profile-aware source definitions."""
        pd = self.profile_dir
        profile = self.profile

        sources = {
            "sessions": {
                "backend": "lcm",
                "profiles": [profile],
                "description": f"LCM sessions for {profile}",
            },
            "gateway_log": {
                "path": f"{pd}/logs/gateway.log",
                "description": f"Gateway log for {profile}",
            },
            "memory_md": {
                "path": f"{pd}/MEMORY.md",
                "description": f"L1 memory for {profile}",
            },
            "soul_md": {
                "path": f"{pd}/SOUL.md",
                "description": f"Role soul for {profile}",
            },
            "agents_md": {
                "path": f"{pd}/AGENTS.md",
                "description": f"Agent rules for {profile}",
            },
            "identity_md": {
                "path": f"{pd}/IDENTITY.md",
                "description": f"Identity for {profile}",
            },
        }

        # In global mode, scan all profiles
        if self.mode == "global":
            global_profiles = self.global_profiles or self._discover_profiles()
            sources["sessions"]["profiles"] = global_profiles
            # Keep conductor's circuit files as the central target
            # but add all-profile session scanning

        self.sources = sources

    def _load_circuit_weights(self):
        """Load profile-aware circuit weights."""
        if self.circuit_weights:
            return  # already loaded from file

        profile = self.profile
        weights = DEFAULT_CIRCUIT_WEIGHTS.get(profile) or DEFAULT_CIRCUIT_WEIGHTS["default"]
        self.circuit_weights = weights.copy()

    def _discover_profiles(self) -> List[str]:
        """Discover all profiles in the profiles directory."""
        profiles = []
        pd = Path(self.profiles_dir)
        if not pd.exists():
            return ["conductor"]
        for d in pd.iterdir():
            if d.is_dir() and (d / "SOUL.md").exists():
                profiles.append(d.name)
        return profiles if profiles else ["conductor"]

    # ── Helpers ──────────────────────────────────────────────────

    def get_phase_model(self, phase: str) -> PhaseModelConfig:
        """Get model config for a phase. Falls back to Hermes defaults if unset."""
        return self.phase_models.get(phase, PhaseModelConfig())

    def get_provider_url(self, provider: str) -> str:
        """Get the API base URL for a provider (from PROVIDER_ENDPOINTS or config)."""
        if provider in self._provider_base_url:
            return self._provider_base_url[provider]
        endpoint = PROVIDER_ENDPOINTS.get(provider)
        if endpoint:
            return endpoint["base_url"]
        return ""

    def get_circuit_weight(self, filename: str) -> float:
        """Get weight for a circuit file. Returns 0.0 if not found."""
        for cw in self.circuit_weights:
            if cw.path == filename:
                return cw.weight
        # Check universal files
        if filename in UNIVERSAL_CIRCUIT_FILES:
            return 0.50  # moderate default for unknown config
        return 0.30  # low default for non-circuit files

    def get_circuit_path(self, filename: str) -> str:
        """Get full path to a circuit file."""
        return str(Path(self.profile_dir) / filename)

    def is_phase_enabled(self, phase: str) -> bool:
        """Check if a phase is enabled."""
        return self.enabled and self.phase_enabled.get(phase, True)

    def to_dict(self) -> dict:
        """Serialize to dict for evol.json."""
        return {
            "mode": self.mode,
            "enabled": self.enabled,
            "edit_mode": self.edit_mode,
            "cooldown_minutes": self.cooldown_minutes,
            "express_cooldown_hours": self.express_cooldown_hours,
            "idle_trigger_minutes": self.idle_trigger_minutes,
            "activity_trigger_tasks": self.activity_trigger_tasks,
            "max_retries_per_phase": self.max_retries_per_phase,
            "max_cycles_per_day": self.max_cycles_per_day,
            "phases": self.phase_enabled,
            "phase_models": {
                phase: pm.to_dict() for phase, pm in self.phase_models.items()
            },
            "global_profiles": self.global_profiles or self._discover_profiles(),
            "circuit_weights": [
                {"path": cw.path, "weight": cw.weight, "role": cw.role}
                for cw in self.circuit_weights
            ],
        }

    def save(self):
        """Save current config to evol.json."""
        self._save_to_file()

    @classmethod
    def from_env(cls) -> "EvolConfig":
        """Create EvolConfig from environment — auto-detects profile, reads config files, applies env overrides."""
        return cls()

    def __repr__(self) -> str:
        return (
            f"EvolConfig(profile={self.profile!r}, mode={self.mode!r}, "
            f"enabled={self.enabled}, edit_mode={self.edit_mode!r}, "
            f"phases={sum(self.phase_enabled.values())}/5 enabled)"
        )
