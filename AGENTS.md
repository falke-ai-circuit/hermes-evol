# AGENTS.md — hermes-evol (Conductor Delegation Rules)

> This file is referenced by the conductor profile when interacting with this repo.
> See `~/.hermes/profiles/conductor/AGENTS.md` for the full gate set.

## Repo-Specific Rules

### Before Any Edit
1. Load `.github/skills/akis-workflow/SKILL.md` (G0)
2. Query `project_knowledge.json` for gotchas and hot cache (G1)
3. Preload relevant skills: `plugin-dev`, `evol` (G3)

### After Any Edit
1. Run `python .github/scripts/knowledge.py --update`
2. Verify: `python -c "from hermes_evol.registry import *; from hermes_evol.engine import *; print('imports OK')"`
3. Clear `__pycache__/` directories

### Git Workflow
- Commit format: `v<version> — <description>`
- Tag format: `v<version>` annotated with release notes
- Push: `git push origin main --tags`
- Never force-push without explicit approval
