---
name: evol-explore
description: Phase 4 of evol-cycle. Find solutions/betterments outside the system: web search via SearXNG, and ask the target agent directly (spawn as subagent if active, else write to pending_questions.md). Returns external knowledge + agent_perspective.
last_used: 2026-06-04
---

# EXPLORE — External Discovery + Agent Voice

> Find solutions outside the system. Always ask the target agent what *it* wants. Web is bonus, not required.

## When to load

Load when starting phase 4 of `evol-cycle`. Inputs: reflect gaps + pending_questions.

## Output contract

```python
{
  "external": [{"url": str, "title": str, "snippet": str, "relevance": float}],
  "agent_perspective": str | {"status": "queued", "path": "..."},
  "unanswered": [str]  # what's still unknown
}
```

## Algorithm

### Step 1: Ask the target agent (mandatory)

```python
def ask_target(agent, question, session_active):
    if session_active:
        # Spawn as subagent via hermes delegation
        return delegate_task(goal=question, agent_profile=agent)
    else:
        # Persist for next session
        with open(f"~/.hermes/profiles/{agent}/pending_questions.md", "a") as f:
            f.write(f"\n## {iso_now()}\n{question}\n")
        return {"status": "queued", "path": "pending_questions.md"}
```

**Detection of "session active":** check if `~/.hermes/profiles/{agent}/sessions/session_*.json` has any file modified in the last 5 minutes.

### Step 2: External web search (best effort)

```python
def web_search(query):
    if not SEARXNG_URL:
        return []
    try:
        r = requests.post(f"{SEARXNG_URL}/search", data={"q": query, "format": "json"}, timeout=10)
        return r.json().get("results", [])[:3]
    except Exception:
        return []
```

Skip if `SEARXNG_URL` is unset or unreachable. Log the skip, don't fail the phase.

### Step 3: Compile unanswered

Combine: questions reflect couldn't answer + questions target agent couldn't answer + questions web search couldn't answer.

## LLM use

If web returns 0 results AND agent_perspective is queued AND gaps > 3, call LLM to summarize what we have. Otherwise the structured output is enough.

## Anti-Patterns

- ⛔ Spawning target agent without informing it — pass the question explicitly
- ⛔ Web search without query formulation — derive queries from reflect.gaps, not random
- ⛔ Reporting `external: []` as success — it means EXPLORE failed, not "no externals available"

## Gotchas

| Problem | Root cause | Fix |
|---------|-----------|-----|
| `delegate_task` not available in this profile | toolset restriction | fallback to pending_questions.md |
| SEARXNG_URL not set | .env not sourced | check `os.getenv("SEARXNG_URL")` first |
| Target agent session_active check is wrong | mtime check vs file write | also check if `gateway_state.json` shows it as `active_agents > 0` |

## Run

```bash
python ~/.hermes/profiles/evol/skills/evol-cycle/phases/explore/scripts/ask_target.py \
  /tmp/evol_absorb_<target>.json /tmp/evol_reflect_<target>.json \
  -o /tmp/evol_explore_<target>.json
```

## Evolution Log

| Date | Promotion | Source |
|------|-----------|--------|
| 2026-06-04 | Initial | spec at `references/six-phase-skill-layout.md` |
<!-- last_used: 2026-06-04 -->
