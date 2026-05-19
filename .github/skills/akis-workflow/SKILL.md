---
name: akis-workflow
description: AKIS (Agent Knowledge Integration System) — 8-gate workflow for repo-based agent work. Must be loaded before any edit to a repo.
last_used: 2026-05-18
---

# AKIS Workflow — Agent Knowledge Integration System

> **G0: Load this skill before ANY edit to the repo.**
> AKIS ensures every agent working on this repo follows a consistent knowledge loop:
> know what's been done → plan the change → execute with verification → record what happened.

## 8-Gate Workflow

| Gate | Name | Action | Tool |
|------|------|--------|------|
| **G0** | Context Load | Load this skill | `skill_view("akis-workflow")` |
| **G1** | Knowledge Query | Query `project_knowledge.json` for gotchas, hot cache, recent changes | `read_file("project_knowledge.json")` |
| **G2** | Structured Plan | Create structured TODO with clear steps | `todo` tool |
| **G3** | Skill Preload | Preload relevant domain skills (evol, plugin-dev, circuit-file-editing) | `skill_view` |
| **G4** | Intent Announce | Announce what you're doing and why | Message to user |
| **G5** | Execute + Verify | Implement changes, verify with imports/format checks | `terminal`, `patch`, `write_file` |
| **G6** | Workflow Log | Append to `.github/workflow-log.jsonl` — what was done, why, outcome | `write_file` (append) |
| **G7** | Knowledge Update | Run `python .github/scripts/knowledge.py --update` to refresh `project_knowledge.json` | `terminal` |

## G1: project_knowledge.json Format

```json
{
  "project": "hermes-evol",
  "last_updated": "ISO-8601",
  "hot_cache": [
    {"topic": "...", "weight": 0.85, "last_hit": "ISO-8601", "files": ["..."], "note": "..."}
  ],
  "gotchas": [
    {"id": "...", "problem": "...", "root_cause": "...", "fix": "...", "severity": "HIGH|MED|LOW", "last_hit": "ISO-8601", "hits": 5}
  ],
  "recent_changes": [
    {"version": "...", "date": "ISO-8601", "summary": "...", "files": ["..."]}
  ],
  "architecture": {
    "files": {"file": "role"},
    "phases": ["ABSORB", "REFLECT", "EXPLORE", "EXPRESS", "MEMORIZE"],
    "providers": {"phase": "provider"}
  }
}
```

## G5: Verification Checklist

Before considering work "done":
- [ ] `python -c "from hermes_evol.registry import *; from hermes_evol.engine import *; print('imports OK')"`
- [ ] `rm -rf hermes_evol/__pycache__/ __pycache__/`
- [ ] No hardcoded defaults — everything from `evol.json` or `EvolConfig`
- [ ] Circuit file edits follow `circuit-file-editing` SKILL.md format (tables, `§` markers, YAML frontmatter)
- [ ] Search backends configurable, not hardcoded

## G6: Workflow Log Format

```jsonl
{"ts": "ISO-8601", "gate": "G5", "agent": "conductor", "action": "patch", "files": ["..."], "summary": "..."}
```

## G7: knowledge.py Behavior

Running `python .github/scripts/knowledge.py --update`:
1. Scans `evol.jsonl` for recent cycle patterns
2. Extracts gotchas from `CLAUDE.md` gotcha section
3. Updates `project_knowledge.json` hot_cache with currently relevant topics
4. Updates `last_updated` timestamp
5. Bumps `hits` on gotchas that occurred during this session

## Anti-Patterns

| ❌ Never | Why |
|----------|-----|
| Skip G1 (knowledge query) | Miss existing gotchas → repeat known mistakes |
| Edit without G3 (skill preload) | Miss circuit-file-editing format rules |
| Skip G7 (knowledge update) | `project_knowledge.json` goes stale → next agent repeats mistakes |
| Commit without G6 (workflow log) | No audit trail — can't trace why changes were made |
| Hardcode defaults in code | Must read from `evol.json` — user-configurable |

## Evolution Log

| Date | Promotion | Source |
|------|-----------|--------|
| 2026-05-18 | Created — 8-gate AKIS workflow for hermes-evol repo | Conductor / Goran mandate |
