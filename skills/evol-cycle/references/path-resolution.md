---
name: path-resolution
description: How `_lib.profiles_root()` resolves the profiles directory. The order of preference, the bug it had, the test that catches a regression, and the env vars to set.
last_used: 2026-06-04
---

# Path Resolution

## The problem

EVOL's phase scripts need to read/write `SOUL.md`, `AGENTS.md`, `MEMORY.md`, `IDENTITY.md` in the target agent's profile dir. On different hosts, that path lives in different places:

- `~/.hermes/profiles/{agent}/` (most common)
- `/opt/data/profiles/{agent}/` (the hermes user on this host; ~ resolves to /opt/data)
- `$HERMES_CONFIG_DIR/profiles/{agent}/` (configurable)
- `$HERMES_DATA/profiles/{agent}/` (legacy)
- `~/config_root/profiles/{agent}/` (a default that doesn't exist on this host but might on others)

Hardcoding any one of these breaks the moment a future host uses a different layout. The conductor's `circuit-file-editing` skill has the same rule.

## The resolution chain (current implementation in `_lib.py`)

```python
def profiles_root() -> Path:
    """Resolve profiles dir. Priority: HERMES_CONFIG_DIR > HERMES_DATA + /profiles > ~/.hermes/profiles > ~/config_root/profiles."""
    explicit = os.environ.get('HERMES_CONFIG_DIR')
    if explicit:
        return Path(explicit) / 'profiles'
    data = os.environ.get('HERMES_DATA')
    if data:
        return Path(data) / 'profiles'
    home_hermes = Path.home() / '.hermes' / 'profiles'
    if home_hermes.exists():
        return home_hermes
    return Path.home() / 'config_root' / 'profiles'
```

**Priority order:**
1. `$HERMES_CONFIG_DIR/profiles` — explicit override
2. `$HERMES_DATA/profiles` — legacy env var
3. `~/.hermes/profiles` if it exists — the typical hermes user setup
4. `~/config_root/profiles` — last-resort default

## The bug that bit us (2026-06-04)

The original implementation was:

```python
# BAD
return Path.home() / 'config_root' / 'profiles'
```

This returned a non-existent path on the hermes user setup, where `~` = `/opt/data` and the actual profiles dir is `/opt/data/.hermes/profiles/`. The bug surfaced when EXPLORE tried to write to `pending_questions.md` and got `FileNotFoundError: profile dir not found: /opt/data/config_root/profiles/analyst`.

**The fix:** check `~/.hermes/profiles` *before* falling back to `~/config_root/profiles`. The first version of the code didn't have the `home_hermes.exists()` check, so it always fell through to the wrong default.

**Lesson:** never trust a "default" without checking the env first. The Path.home() / 'config_root' / 'profiles' default is what we'd want on a non-hermes user; for the actual hermes user, the home-relative .hermes path is the right one.

## How to test the resolver

```bash
python3 ~/.hermes/profiles/evol/skills/evol-cycle/scripts/test_path_resolution.py
```

The test runs the resolver under 6 scenarios:

| Scenario | HERMES_CONFIG_DIR | HERMES_DATA | HOME | Expected |
|---|---|---|---|---|
| 1. Explicit override | `/custom/cfg` | unset | anything | `/custom/cfg/profiles` |
| 2. HERMES_DATA legacy | unset | `/data` | anything | `/data/profiles` |
| 3. ~/.hermes exists | unset | unset | `/opt/data` | `/opt/data/.hermes/profiles` |
| 4. ~ only | unset | unset | `/nonexistent` | `/nonexistent/config_root/profiles` (fallback) |
| 5. Both envs set | `/a` | `/b` | anything | `/a/profiles` (explicit wins) |
| 6. Empty strings | `""` | `""` | `/opt/data` | `/opt/data/.hermes/profiles` (empty falls through) |

The test sets the env vars, calls `profiles_root()`, checks the result, and prints PASS/FAIL. If a future change to the resolver breaks one of these, the test catches it.

## Anti-pattern: hardcoding `/opt/data/profiles/`

`/opt/data/profiles/` only works for the hermes user on this host. On any other host, that path doesn't exist. **Never write a phase script with a hardcoded path.** Always call `profiles_root()` and `profile_dir(agent)`.

## The `_lib.py::profile_dir` raises

`profile_dir(agent)` calls `profiles_root() / agent` and raises `FileNotFoundError` if the dir doesn't exist. This is intentional — silent path-typos produce silent-no-op scripts. Raising forces the caller to handle the path resolution failure explicitly.

## Source of truth

`phases/_lib.py::profiles_root` and `phases/_lib.py::profile_dir` are the algorithm. This file is a working summary.

## Evolution Log

| Date | Promotion | Source |
|------|-----------|--------|
| 2026-06-04 | Initial — added `home_hermes.exists()` check after the no-env-vars path returned `~/config_root/profiles/` on a system where that didn't exist | analyst cycle #2 EXPLORE phase |
<!-- last_used: 2026-06-04 -->
