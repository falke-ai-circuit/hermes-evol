#!/usr/bin/env python3
"""Test round-trip integrity for EvolConfig (load → save → load) and API key masking."""
import json
import os
import sys
import tempfile
from pathlib import Path

# Ensure the plugin is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hermes_evol.config import EvolConfig, PhaseModelConfig

TEST_PROFILE = "conductor"

def test_phase_model_key_masking():
    """PhaseModelConfig.to_dict() masks API keys"""
    pm = PhaseModelConfig(provider="venice", model="glm-4", api_key="sk-1234567890abcdef")
    d = pm.to_dict()

    assert d["api_key"] == "sk-1...cdef", f"Expected masked key, got: {d['api_key']}"
    assert "1234567890" not in d["api_key"], "Plaintext API key leaked!"

    # Short key (8 chars)
    pm2 = PhaseModelConfig(provider="x", model="y", api_key="12345678")
    d2 = pm2.to_dict()
    assert d2["api_key"] == "***", f"Expected ***, got: {d2['api_key']}"

    # Very short key
    pm3 = PhaseModelConfig(provider="x", model="y", api_key="abc")
    d3 = pm3.to_dict()
    assert d3["api_key"] == "***", f"Expected ***, got: {d3['api_key']}"

    # Empty key
    pm4 = PhaseModelConfig(provider="x", model="y", api_key="")
    d4 = pm4.to_dict()
    assert d4["api_key"] == "", f"Expected empty, got: {d4['api_key']}"

    print("✓ PhaseModelConfig API key masking: PASS")

def test_from_dict_skips_masked_keys():
    """PhaseModelConfig.from_dict() skips masked API keys (round-trip safety)"""
    # A masked key should be treated as empty
    pm = PhaseModelConfig.from_dict({"api_key": "sk-1...cdef", "provider": "x", "model": "y"})
    assert pm.api_key == "", f"Expected empty, got: {pm.api_key!r}"

    pm2 = PhaseModelConfig.from_dict({"api_key": "***", "provider": "x", "model": "y"})
    assert pm2.api_key == "", f"Expected empty, got: {pm2.api_key!r}"

    # A real key should pass through
    pm3 = PhaseModelConfig.from_dict({"api_key": "sk-real-key-no-ellipsis", "provider": "x", "model": "y"})
    assert pm3.api_key == "sk-real-key-no-ellipsis", f"Expected real key, got: {pm3.api_key!r}"

    print("✓ PhaseModelConfig.from_dict() masked-key skip: PASS")

def test_evolconfig_roundtrip():
    """EvolConfig round-trip: all fields survive save → load"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set up a minimal profile directory
        profile_dir = Path(tmpdir) / "profiles" / TEST_PROFILE
        profile_dir.mkdir(parents=True)
        (profile_dir / "SOUL.md").write_text("# test soul")
        (profile_dir / "config.yaml").write_text("model:\n  provider: ollama-cloud\n  default: deepseek-v4-pro\n")

        # Override paths via env
        os.environ["HERMES_CONFIG_DIR"] = tmpdir
        os.environ["HERMES_PROFILE"] = TEST_PROFILE

        try:
            # Create config with non-default values for ALL fields
            cfg = EvolConfig(profile=TEST_PROFILE)

            # Set every field that to_dict() now serializes
            cfg.mode = "global"
            cfg.enabled = False
            cfg.edit_mode = "auto"
            cfg.operation_mode = "session"
            cfg.cooldown_minutes = 60
            cfg.express_cooldown_hours = 6
            cfg.idle_trigger_minutes = 15
            cfg.activity_trigger_tasks = 2
            cfg.phase_triggers = {"reflect": 5, "express": 4, "explore": 3, "memorize": 2}
            cfg.fallback_cycle_hours = 12
            cfg.express_style = "synthesis"
            cfg.explore_query_limit = 5
            cfg.session_scope = "profile"
            cfg.max_retries_per_phase = 2
            cfg.max_cycles_per_day = 4
            cfg.search_backend = "duckduckgo"
            cfg.search_backend_url = "https://searx.example.com"
            cfg.search_api_key = "sk-search-key-abcdef123456"
            cfg.phase_enabled = {"absorb": True, "reflect": False, "explore": True, "express": False, "memorize": True}
            cfg.phase_models["reflect"].provider = "venice"
            cfg.phase_models["reflect"].model = "glm-4"
            cfg.phase_models["reflect"].api_key = "sk-venice-key-9999"
            cfg.global_profiles = ["conductor", "coder", "shadow"]
            cfg.circuit_weights = []  # will be auto-populated

            # Save to evol.json
            cfg.profile_dir = str(profile_dir)
            data = cfg.to_dict()

            # Save and reload
            config_path = profile_dir / "evol.json"
            config_path.write_text(json.dumps(data, indent=2))

            # Now simulate a fresh load (new object from the saved file)
            cfg2 = EvolConfig(profile=TEST_PROFILE)
            cfg2.profile_dir = str(profile_dir)  # ensure it uses our tmp
            cfg2.profiles_dir = str(Path(tmpdir) / "profiles")
            cfg2._load_from_file()

            # --- Verify all fields round-tripped ---
            assert cfg2.mode == "global", f"mode: {cfg2.mode}"
            assert cfg2.enabled == False, f"enabled: {cfg2.enabled}"
            assert cfg2.edit_mode == "auto", f"edit_mode: {cfg2.edit_mode}"
            assert cfg2.operation_mode == "session", f"operation_mode: {cfg2.operation_mode}"
            assert cfg2.cooldown_minutes == 60, f"cooldown_minutes: {cfg2.cooldown_minutes}"
            assert cfg2.express_cooldown_hours == 6, f"express_cooldown_hours: {cfg2.express_cooldown_hours}"
            assert cfg2.idle_trigger_minutes == 15, f"idle_trigger_minutes: {cfg2.idle_trigger_minutes}"
            assert cfg2.activity_trigger_tasks == 2, f"activity_trigger_tasks: {cfg2.activity_trigger_tasks}"
            assert cfg2.phase_triggers == {"reflect": 5, "express": 4, "explore": 3, "memorize": 2}, f"phase_triggers: {cfg2.phase_triggers}"
            assert cfg2.fallback_cycle_hours == 12, f"fallback_cycle_hours: {cfg2.fallback_cycle_hours}"
            assert cfg2.express_style == "synthesis", f"express_style: {cfg2.express_style}"
            assert cfg2.explore_query_limit == 5, f"explore_query_limit: {cfg2.explore_query_limit}"
            assert cfg2.session_scope == "profile", f"session_scope: {cfg2.session_scope}"
            assert cfg2.max_retries_per_phase == 2, f"max_retries_per_phase: {cfg2.max_retries_per_phase}"
            assert cfg2.max_cycles_per_day == 4, f"max_cycles_per_day: {cfg2.max_cycles_per_day}"
            assert cfg2.search_backend == "duckduckgo", f"search_backend: {cfg2.search_backend}"
            assert cfg2.search_backend_url == "https://searx.example.com", f"search_backend_url: {cfg2.search_backend_url}"

            # --- Security: API keys should be masked in saved file, NOT plaintext ---
            saved_text = config_path.read_text()
            assert "sk-search-key-abcdef123456" not in saved_text, "search_api_key leaked to disk!"
            assert "sk-venice-key-9999" not in saved_text, "phase model api_key leaked to disk!"
            print("✓ API keys masked on disk: PASS")

            # --- Security: after load, masked keys are treated as empty ---
            # search_api_key should be empty (mask was loaded → skipped)
            assert cfg2.search_api_key == "", f"search_api_key should be empty after loading masked key, got: {cfg2.search_api_key!r}"
            # Phase model api_key should also be empty
            reflect_model = cfg2.phase_models.get("reflect")
            assert reflect_model.api_key == "", f"reflect api_key should be empty, got: {reflect_model.api_key!r}"
            print("✓ Masked keys properly skipped on reload: PASS")

            # --- Verify non-key fields round-tripped correctly ---
            assert cfg2.phase_enabled["reflect"] == False, f"reflect phase: {cfg2.phase_enabled['reflect']}"
            assert cfg2.phase_enabled["express"] == False, f"express phase: {cfg2.phase_enabled['express']}"
            assert cfg2.global_profiles == ["conductor", "coder", "shadow"], f"global_profiles: {cfg2.global_profiles}"
            assert cfg2.phase_models["reflect"].provider == "venice", f"reflect provider: {cfg2.phase_models['reflect'].provider}"
            assert cfg2.phase_models["reflect"].model == "glm-4", f"reflect model: {cfg2.phase_models['reflect'].model}"

            print("✓ All 9 missing fields round-tripped: PASS")
            print("✓ Phase toggles + phase_models + global_profiles: PASS")

        finally:
            del os.environ["HERMES_CONFIG_DIR"]
            del os.environ["HERMES_PROFILE"]


def test_to_dict_has_all_loadable_fields():
    """Verify to_dict() keys cover everything _load_from_file() reads"""
    cfg = EvolConfig(profile=TEST_PROFILE)
    d = cfg.to_dict()

    _loadable_fields = [
        "mode", "enabled", "edit_mode", "operation_mode",
        "cooldown_minutes", "express_cooldown_hours",
        "idle_trigger_minutes", "activity_trigger_tasks",
        "phase_triggers", "fallback_cycle_hours",
        "express_style", "explore_query_limit", "session_scope",
        "max_retries_per_phase", "max_cycles_per_day",
        "search_backend", "search_backend_url", "search_api_key",
        "phases", "phase_models", "global_profiles", "circuit_weights",
    ]

    missing = [f for f in _loadable_fields if f not in d]
    assert not missing, f"Fields missing from to_dict(): {missing}"

    print(f"✓ {len(_loadable_fields)} fields present in to_dict(): PASS")


if __name__ == "__main__":
    print("=== EVOL Config Round-Trip + Security Tests ===\n")
    try:
        test_phase_model_key_masking()
        test_from_dict_skips_masked_keys()
        test_to_dict_has_all_loadable_fields()
        test_evolconfig_roundtrip()
        print("\n✅ ALL TESTS PASSED")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
