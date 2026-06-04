# Cycle Migration Recipe — Replacing the Plugin with Skills

> The plugin-based 5-phase flow (`evol_reflect`, `evol_explore`, `evol_speak`, `evol_memorize`, `evol_cycle`, `evol_status`, `evol_config`, `evol_material`, `evol_task_end`) is **deprecated and removed** as of 2026-06-04. This is the one-time recipe that replaced it. Re-run only if migrating a new environment or recovering from incomplete migration.

## When this is needed

- Setting up evol on a new machine / container.
- Recovering after the plugin has been accidentally re-enabled.
- Auditing an environment to confirm the migration is complete.

## Step 1: Quarantine old `evol.jsonl` in every profile

The old log is contaminated with `applied: true` lies. Quarantine, don't delete.

```bash
for p in evol analyst conductor coder reviewer researcher architect orchestrator operative shadow valmet; do
    d=~/.hermes/profiles/$p
    if [ -f "$d/evol.jsonl" ] && [ ! -f "$d/evol.jsonl.historical-2026-06-04" ]; then
        cp "$d/evol.jsonl" "$d/evol.jsonl.historical-2026-06-04"
        echo "quarantined: $d/evol.jsonl"
    fi
done
```

Optionally, re-import as `untrusted: true` so REFLECT can still see them but doesn't promote them:

```python
import json
from pathlib import Path
src = Path('/opt/data/profiles/analyst/evol.jsonl.historical-2026-06-04')
dst = Path('/opt/data/profiles/analyst/evol.jsonl')
with src.open() as fin, dst.open('w') as fout:
    for line in fin:
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
            e['untrusted'] = True
            e['source'] = 'historical-2026-06-04'
            fout.write(json.dumps(e) + '\n')
        except json.JSONDecodeError:
            pass
```

The same recipe applies to `evol.json` (cycle config). Quarantine, start fresh.

## Step 2: Disable the `evol` toolset in every profile config

Idempotent. Adds `'evol'` to the `disabled_toolsets` list if not already present, creates the list if missing.

```python
import re
from pathlib import Path

PROFILES = [
    'analyst', 'architect', 'coder', 'conductor', 'evol',
    'operative', 'orchestrator', 'researcher', 'reviewer', 'shadow', 'valmet',
]

for profile in PROFILES:
    cfg = Path(f'~/.hermes/profiles/{profile}/config.yaml')
    if not cfg.exists():
        continue
    text = cfg.read_text()
    if "'evol'" in text or '"evol"' in text:
        continue  # already disabled
    if 'disabled_toolsets' in text:
        new_text = re.sub(
            r'disabled_toolsets:\s*\[([^\]]*)\]',
            lambda m: f'disabled_toolsets: [{m.group(1).strip().rstrip(",") + ", " if m.group(1).strip() else ""}\'evol\']',
            text, count=1,
        )
    else:
        # Insert after model:/providers: block
        lines = text.split('\n')
        idx = 0
        for i, line in enumerate(lines):
            if line.startswith('model:') or line.startswith('providers:'):
                idx = i + 1
                while idx < len(lines) and lines[idx].startswith(' '):
                    idx += 1
                break
        lines.insert(idx, "agent:\n  disabled_toolsets: ['evol']\n")
        new_text = '\n'.join(lines)
    cfg.write_text(new_text)
```

**Common pitfall:** 5 profiles (`architect`, `coder`, `operative`, `researcher`, `reviewer`) don't have a `toolsets:` key — they fall back to the default. The first regex pass misses them. The second pass (insert under `agent:`) catches them. Run both.

## Step 3: Verify the plugin is unreachable

After a config edit, the gateway must be restarted for `disabled_toolsets` to take effect. The simplest trigger is an s6-supervise restart, which happens automatically when any other service in `/etc/s6-overlay/s6-rc.d/` is touched. Or wait for the next natural restart.

```bash
# Verify in the running gateway's environment
cat /proc/$(cat ~/.hermes/profiles/evol/gateway.pid | python3 -c "import sys,json; print(json.load(sys.stdin)['pid'])")/environ \
  | tr '\0' '\n' | grep -E "_HERMES_GATEWAY|HERMES_PROFILE"

# Verify the toolset is gone
python -c "
import os
os.environ['HERMES_PROFILE'] = 'evol'
os.environ['HERMES_HOME'] = '/opt/data/profiles/evol'
from hermes_cli.config import load_config
cfg = load_config()
print('toolsets:', cfg.get('toolsets'))
print('disabled:', cfg.get('agent', {}).get('disabled_toolsets', []))
"
```

If `disabled: ['evol']` shows up and the `evol_*` tools are not in your available tool list, the migration is complete.

## Step 4: Build the 6 phase skills

Already built. See:

- `~/.hermes/profiles/evol/skills/evol-cycle/SKILL.md` (orchestrator)
- `~/.hermes/profiles/evol/skills/evol-cycle/phases/{absorb,reflect,adapt,explore,express,memorize}/SKILL.md` (per-phase)
- `~/.hermes/profiles/evol/skills/evol-cycle/phases/*/scripts/*.py` (canonical implementations)
- `~/.hermes/profiles/evol/skills/evol-cycle/run.sh` (bash entry point)

## Step 5: Run a cycle on a test profile

```bash
SEARXNG_URL=http://100.78.148.26:8080 bash ~/.hermes/profiles/evol/skills/evol-cycle/run.sh analyst
```

Expected output: all 6 phases complete, surfaced_to_user summary, `verified_mutations` count (often 0 on a clean run — empty plan is valid).

## What to NOT do

- **Do not delete the plugin files.** They stay on disk for audit. The `disabled_toolsets` config is the only thing keeping them silent.
- **Do not re-enable the plugin** because the skill flow is "slow." The skill flow runs in ~2s per phase. The plugin was always slower (LLM call per phase) and lied about its writes.
- **Do not bypass ADAPT.** "Reflect is enough" was the failure mode that produced 36 evol.jsonl entries with no actual file changes. ADAPT is the diff-check. Removing it removes the only thing keeping the cycle honest.
- **Do not import old evol.jsonl as trusted data.** Always re-import with `untrusted: true`. The plugin's `applied: true` field cannot be trusted.

## What to update in this doc

If the migration recipe changes (new profile names, new config schema, new toolset name), update the lists in steps 1 and 2. The 4 steps themselves are stable.
