#!/usr/bin/bash
# Run a full 6-phase evol cycle on a target agent.
# Order: ABSORB → REFLECT → EXPRESS → EXPLORE → ADAPT → MEMORIZE
#
# Usage: run.sh <target_agent>
#
# Each phase writes /tmp/evol_<phase>_<target>.json
# Final summary printed to stdout.

set -euo pipefail

TARGET="${1:-}"
if [ -z "$TARGET" ]; then
    echo "Usage: $0 <target_agent>" >&2
    exit 1
fi

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ABSORB_OUT="/tmp/evol_absorb_${TARGET}.json"
REFLECT_OUT="/tmp/evol_reflect_${TARGET}.json"
EXPRESS_OUT="/tmp/evol_express_${TARGET}.json"
EXPLORE_OUT="/tmp/evol_explore_${TARGET}.json"
ADAPT_OUT="/tmp/evol_adapt_${TARGET}.json"
MEMORIZE_OUT="/tmp/evol_memorize_${TARGET}.json"

PY="${PYTHON:-/opt/hermes/.venv/bin/python}"

echo "═══ EVOL cycle on profile: $TARGET ═══"

echo ""
echo "▶ Phase 1/6: ABSORB"
"$PY" "$SKILL_DIR/phases/absorb/scripts/collect_state.py" "$TARGET" -o "$ABSORB_OUT"

echo ""
echo "▶ Phase 2/6: REFLECT"
"$PY" "$SKILL_DIR/phases/reflect/scripts/pattern_graph.py" "$ABSORB_OUT" -o "$REFLECT_OUT"

echo ""
echo "▶ Phase 3/6: EXPRESS  (target agent's POV)"
"$PY" "$SKILL_DIR/phases/express/scripts/monologue.py" "$ABSORB_OUT" "$REFLECT_OUT" -o "$EXPRESS_OUT"

echo ""
echo "▶ Phase 4/6: EXPLORE  (targeted by express's gap_vector)"
"$PY" "$SKILL_DIR/phases/explore/scripts/ask_target.py" "$ABSORB_OUT" "$REFLECT_OUT" "$EXPRESS_OUT" -o "$EXPLORE_OUT"

echo ""
echo "▶ Phase 5/6: ADAPT  (real instructions, tier-aware)"
"$PY" "$SKILL_DIR/phases/adapt/scripts/mismatch_detector.py" "$ABSORB_OUT" "$REFLECT_OUT" "$EXPRESS_OUT" "$EXPLORE_OUT" -o "$ADAPT_OUT"

echo ""
echo "▶ Phase 6/6: MEMORIZE  (diff-checked, format-validated)"
"$PY" "$SKILL_DIR/phases/memorize/scripts/diff_apply.py" "$ADAPT_OUT" "$EXPRESS_OUT" "$ABSORB_OUT" -o "$MEMORIZE_OUT"

echo ""
echo "═══ Cycle complete ═══"
echo ""
echo "─── express voice ───"
"$PY" -c "
import json
d = json.load(open('$EXPRESS_OUT'))
print(f'voice: {d[\"voice\"]}')
print(f'voice_detail: {d[\"voice_detail\"][:120]}')
print(f'gap_vector_for_explore: {len(d[\"gap_vector_for_explore\"])} queries')
"
echo ""
echo "─── explore results ───"
"$PY" -c "
import json
d = json.load(open('$EXPLORE_OUT'))
print(f'queries_used: {d[\"queries_used\"]}')
print(f'external hits: {len(d[\"external\"])}')
for e in d['external'][:3]:
    print(f'  - {e.get(\"title\",\"\")[:80]}')
    print(f'    {e.get(\"url\",\"\")[:100]}')
print(f'agent_perspective: {d[\"agent_perspective\"].get(\"status\",\"?\")}')"
echo ""
echo "─── adapt summary ───"
"$PY" -c "
import json
d = json.load(open('$ADAPT_OUT'))
print(d['summary'])"
echo ""
echo "─── express surfaced ───"
cat "$EXPRESS_OUT" | "$PY" -c "import sys, json; d=json.load(sys.stdin); print(d['surfaced_to_user'])"
echo ""
echo "─── verified_mutations ───"
"$PY" -c "
import sys, json
d = json.load(open('$MEMORIZE_OUT'))
v = d.get('verified_mutations', [])
s = d.get('skipped', [])
print(f'verified: {len(v)}')
for m in v:
    if m.get('type') == 'cleanup':
        print(f'  ✓ CLEANUP: {m[\"total_lines_stripped\"]} garbage lines stripped')
        for f, info in m['files'].items():
            if info.get('verified'):
                print(f'    {f}: {info[\"lines_stripped\"]} lines (sha {info[\"sha_before\"]} -> {info[\"sha_after\"]})')
    else:
        print(f'  ✓ {m[\"file\"]}: {m[\"delta_lines\"]:>+d} lines, tier={m.get(\"tier\",\"?\")}, format={m.get(\"instruction_format\",\"?\")} (sha {m[\"sha_before\"]} -> {m[\"sha_after\"]})')
print(f'skipped: {len(s)}')
for x in s:
    print(f'  ⊘ plan[{x[\"plan_index\"]}]: {x[\"reason\"][:100]}')"
echo ""
echo "─── final surfaced-to-user (post-cycle) ───"
"$PY" -c "
import json
v = json.load(open('$MEMORIZE_OUT'))['verified_mutations']
s = json.load(open('$MEMORIZE_OUT'))['skipped']
e = json.load(open('$EXPRESS_OUT'))
print(f'Cycle: {e[\"target\"]}. Verified: {len(v)}. Skipped: {len(s)}.')
if v:
    print('Real changes made.')"
