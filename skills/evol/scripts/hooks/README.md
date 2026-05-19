# EVOL Phase Hooks

Standardized hook scripts that execute after EVOL phases complete.

## Convention

```json
// evol.json
{
  "phase_post_commands": {
    "express": "python3 skills/evol/scripts/hooks/express-post.py --json",
    "memorize": "python3 skills/evol/scripts/hooks/memorize-post.py --json"
  }
}
```

## Environment

Every hook receives:
- `PHASE_RESULT_FILE` — path to temp JSON with full phase data
- `PHASE_{KEY}` — for each top-level key (e.g., `PHASE_monologue`, `PHASE_mood`)
- `EVOL_PROFILE` — current profile name
- `EVOL_PHASE` — phase name

## Writing a Hook

1. Accept input via `--json` flag + `PHASE_*` env vars
2. Write JSON result to stdout: `{"video": "/path/to/file.mp4", "voice": "..."}`
3. Exit 0 on success, non-zero on failure
4. Keep under 180s (safety timeout)
5. Place in `skills/evol/scripts/hooks/`

## Available Hooks

| Hook | Phase | What it does |
|------|-------|-------------|
| `express-post.py` | express | Voice (edge-tts triple + Falke synth) + portrait (Venice chroma) → MP4 video |

## Phase Result Keys (for PHASE_{KEY} env vars)

| Phase | Keys |
|-------|------|
| absorb | circuit_files, session_summary, timestamp |
| reflect | patterns, signal_summary, anomalies, recommended_action |
| express | monologue, mood, insights, portrait_prompt, circuit_poem, unanswered |
| explore | queries, results, discoveries |
| memorize | items, applied, proposals |
