#!/usr/bin/env bash
# Run a 6-phase evol cycle on every agent profile.
#
# Usage: run_all.sh [--skip-cooldown] [--target NAME]
#
# Without --skip-cooldown, profiles that had a cycle within the last 4h
# are skipped (cooldown gate from the orchestrator SKILL.md).
#
# With --target NAME, only that profile is cycled.
#
# Outputs per-profile JSON to /tmp/evol_*_<target>.json, same as run.sh.
# Prints a final summary table to stdout.

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKIP_COOLDOWN=0
TARGET_ONLY=""

while [ $# -gt 0 ]; do
    case "$1" in
        --skip-cooldown) SKIP_COOLDOWN=1; shift ;;
        --target)        TARGET_ONLY="${2:-}"; shift 2 ;;
        -h|--help)
            sed -n '2,12p' "$0"
            exit 0
            ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

COOLDOWN_SECONDS=$((4 * 3600))   # 4h, matches evol-core SKILL.md
PROFILES=(
    analyst architect coder conductor
    operative orchestrator researcher reviewer
    shadow valmet evol
)

run_one() {
    local target="$1"
    local profile_dir="$HOME/.hermes/profiles/$target"
    if [ ! -d "$profile_dir" ]; then
        echo "  ⊘ $target: profile dir missing" | tee -a /tmp/evol_run_all.log
        return
    fi
    if [ "$SKIP_COOLDOWN" -eq 0 ]; then
        local last_ts=0
        if [ -f "$profile_dir/evol.jsonl" ]; then
            last_ts=$(stat -c %Y "$profile_dir/evol.jsonl" 2>/dev/null || echo 0)
        fi
        local now=$(date +%s)
        local age=$(( now - last_ts ))
        if [ "$age" -lt "$COOLDOWN_SECONDS" ] && [ "$last_ts" -gt 0 ]; then
            local age_h=$(( age / 3600 ))
            echo "  ⏸ $target: cooldown (${age_h}h since last cycle, <4h)" | tee -a /tmp/evol_run_all.log
            return
        fi
    fi
    echo "" | tee -a /tmp/evol_run_all.log
    echo "▶ $target" | tee -a /tmp/evol_run_all.log
    if SEARXNG_URL="${SEARXNG_URL:-}" bash "$SKILL_DIR/run.sh" "$target" 2>&1 | tail -25 | tee -a /tmp/evol_run_all.log; then
        echo "  ✓ $target: cycle complete" | tee -a /tmp/evol_run_all.log
    else
        echo "  ✗ $target: cycle FAILED" | tee -a /tmp/evol_run_all.log
    fi
}

echo "═══ EVOL run_all ═══" | tee /tmp/evol_run_all.log
echo "skip_cooldown=$SKIP_COOLDOWN target_only=${TARGET_ONLY:-<all>}" | tee -a /tmp/evol_run_all.log
echo "started: $(date -Iseconds)" | tee -a /tmp/evol_run_all.log

if [ -n "$TARGET_ONLY" ]; then
    run_one "$TARGET_ONLY"
else
    for p in "${PROFILES[@]}"; do
        run_one "$p"
    done
fi

echo "" | tee -a /tmp/evol_run_all.log
echo "═══ run_all complete ═══" | tee -a /tmp/evol_run_all.log
echo "finished: $(date -Iseconds)" | tee -a /tmp/evol_run_all.log
echo "log: /tmp/evol_run_all.log" | tee -a /tmp/evol_run_all.log
