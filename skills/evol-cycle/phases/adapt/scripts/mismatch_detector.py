#!/usr/bin/env python3
"""ADAPT phase: produce a justified adjustment_plan with REAL INSTRUCTIONS.

Inputs: absorb, reflect, express, explore.
Output: adjustment_plan with format-valid, instruction-shaped proposals.

Key rules (from circuit-file-editing skill, Goran 2026-05-30 permanent):
- SOUL/IDENTITY edits = Evolution Log table rows
- AGENTS edits = Gate table rows (| **G-NAME** | When | Action |)
- MEMORY edits = § Concept (wt:X.XX) — actionable one-liner with fix
- Every entry MUST be a file-adapted actionable instruction, not a name-with-weight

Tier transitions: promote_to_circuit | append_to_memory | demote_to_knowledge | cleanup_garbage
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from _lib import (  # noqa: E402
    profile_dir, classify_tier, validate_proposal_format,
    detect_format, is_garbage_line,
)


def safe_load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as e:
        return {"_error": str(e)}


def file_contains(profile, file_rel: str, text: str) -> bool:
    if not text:
        return False
    try:
        p = profile_dir(profile) / file_rel
    except FileNotFoundError:
        return False
    if not p.exists():
        return False
    return text in p.read_text(errors='replace')


def _instruct_from(kind: str, evidence: str, where: str) -> str:
    """Translate a reflect finding (kind + evidence + where) into a behavioral instruction.

    Returns something like 'verify causal depth and escalate if < 2 levels'.
    This is the Actionable Instruction Principle: the SOUL/AGENTS edit must be
    *what the agent should do*, not a name-with-weight or a copy of the evidence.
    """
    e = (evidence or '').lower()
    if kind == 'stale_doctrine':
        return f"Verify doctrine at {where[:40]} is current; if newer grant exists, supersede the old claim and add cross-reference"
    if kind == 'recurring_orphan':
        return f"When {where[:40]} recurs, escalate to kanban_create with concrete task; do not just log"
    if kind == 'missing_capability':
        return f"Confirm capability at {where[:40]} via direct probe; if confirmed-grant exists, update doctrine to reflect"
    if kind == 'pending_question_unanswered':
        return f"Read pending_questions.md at start of every cycle; if items > 24h old, dispatch or escalate to Goran"
    if 'identity' in e:
        return "Synchronize reflect_count across SOUL/AGENTS/IDENTITY on every cycle; never let them diverge"
    if 'memory' in e and ('gap' in e or 'stale' in e or 'frozen' in e):
        return "Check last MEMORY.md entry date at start of MEMORIZE; if > 7 days stale, append recovery entry before proposing"
    if 'cycle' in e and 'stuck' in e:
        return "Track pattern occurrences; if any pattern recurs 3+ times without resolution, escalate to Goran with evidence"
    return f"Investigate root cause at {where[:60]}; verify causal depth before logging"


def _instruct_from_session(kind: str, evidence: str, where: str, session_signal: dict) -> str:
    """Build an instruction grounded in actual session activity, not just doctrine text.

    session_signal = {first_user_msg, last_msg_preview, message_count, doctrine_hints, model, platform}
    The instruction should reflect what the agent is *actually doing* in sessions.
    """
    base = _instruct_from(kind, evidence, where)
    if not session_signal:
        return base
    msg = session_signal.get('message_count', 0)
    platform = session_signal.get('platform', '')
    model = session_signal.get('model', '')
    first = session_signal.get('first_user_msg', '')
    last = session_signal.get('last_msg_preview', '')
    # Ground the instruction in the agent's actual context
    grounding = []
    if msg:
        grounding.append(f"observed in {msg}-message {platform} session")
    if model:
        grounding.append(f"on {model}")
    if first:
        grounding.append(f"first user intent: '{first[:60]}'")
    if last:
        grounding.append(f"last state: '{last[:60]}'")
    if not grounding:
        return base
    context = '; '.join(grounding[:3])
    return f"{base} (Context: {context})"


def dedupe_adjustment_points(adjustment_points: list) -> list:
    """Collapse adjustment_points by (kind, file, line) so we don't write 28 copies
    of the same instruction when one finding recurs across many lines.

    When collapsing, keep the highest-weight entry and merge evidence.
    """
    if not adjustment_points:
        return []
    by_key = {}
    for ap in adjustment_points:
        # Parse the (file, line) from where like "SOUL.md line 84 vs pending_questions.md"
        where = ap.get('where', '')
        # Strip the " vs ..." suffix if present
        base = where.split(' vs ')[0]
        # Parse file and line
        parts = base.rsplit(' line ', 1)
        if len(parts) == 2:
            file_part, line_part = parts
            try:
                line_num = int(line_part.strip().split()[0])
            except (ValueError, IndexError):
                line_num = 0
        else:
            file_part = where
            line_num = 0
        key = (ap.get('kind', ''), file_part.strip(), line_num)
        if key not in by_key:
            by_key[key] = ap.copy()
            by_key[key]['_merged_count'] = 1
        else:
            # Keep higher weight, merge evidence
            existing = by_key[key]
            if ap.get('weight', 0) > existing.get('weight', 0):
                existing['weight'] = ap.get('weight', 0)
            existing['_merged_count'] = existing.get('_merged_count', 1) + 1
            existing['_merged_evidence'] = (
                (existing.get('evidence', '') + ' || ' + ap.get('evidence', ''))[:500]
            )
    return list(by_key.values())


def derive_session_grounded_context(adj: dict, absorb: dict) -> dict:
    """For a given adjustment_point, find the most recent session that touched
    the file/line in question. Use that session's actual content to ground
    the instruction in real activity, not doctrine-text-only.

    Returns a session_signal dict (or empty dict if no match).
    """
    where = adj.get('where', '')
    base = where.split(' vs ')[0]
    sessions = absorb.get('sessions', [])
    if not sessions:
        return {}
    # Try to find a session whose first user msg or last msg mentions the file/line
    target_file = ''
    target_line = 0
    parts = base.rsplit(' line ', 1)
    if len(parts) == 2:
        target_file = parts[0].strip()
        try:
            target_line = int(parts[1].strip().split()[0])
        except (ValueError, IndexError):
            target_line = 0
    # Return the most recent session as context (simple heuristic)
    if sessions:
        s = sessions[0]
        return {
            'first_user_msg': s.get('first_user_msg', ''),
            'last_msg_preview': s.get('last_msg_preview', ''),
            'message_count': s.get('message_count', 0),
            'doctrine_hints': s.get('doctrine_hints', 0),
            'model': s.get('model', ''),
            'platform': s.get('platform', ''),
        }
    return {}


def build_soul_proposal(adj: dict, target: str, today: str, session_signal: dict = None) -> dict:
    """SOUL.md edits: Evolution Log table row. Source column = full behavioral rule.

    If session_signal is provided, ground the instruction in actual session activity
    so the next session knows the rule came from observed behavior, not doctrine-text alone.
    """
    kind = adj.get('kind', 'reflection')
    if session_signal:
        instruction = _instruct_from_session(kind, adj.get('evidence', ''), adj.get('where', ''), session_signal)
    else:
        instruction = _instruct_from(kind, adj.get('evidence', ''), adj.get('where', ''))
    merged = adj.get('_merged_count', 1)
    merged_note = f" (recurs {merged}x in historical data)" if merged > 1 else ""
    proposed = (
        f"\n| {today} | {kind.replace('_','-')[:24]}-rule (wt:{adj.get('weight', 0.85):.2f}){merged_note} | "
        f"{instruction} |"
    )
    return {
        "file": "SOUL.md",
        "tier": "CIRCUIT",
        "action": "append",
        "proposed_text": proposed,
        "evidence": adj.get('evidence', '')[:300],
        "weight": adj.get('weight', 0.85),
        "instruction_format": "soul_evolution_log_row",
    }


def build_agents_gate_proposal(adj: dict, target: str, today: str, session_signal: dict = None) -> dict:
    """AGENTS.md edits: Gate table row. | **G-NAME** | When | Action |"""
    kind = adj.get('kind', 'reflection')
    gname = f"G-EVOL-{kind.upper().replace('_','')[:8]}-{datetime.now().strftime('%H%M')}"
    when = adj.get('where', 'reflect finding fires')[:80]
    if session_signal:
        action = _instruct_from_session(kind, adj.get('evidence', ''), adj.get('where', ''), session_signal)
    else:
        action = _instruct_from(kind, adj.get('evidence', ''), adj.get('where', ''))
    proposed = (
        f"\n| **{gname}** | **When** {when} | **Action** {action} |"
    )
    return {
        "file": "AGENTS.md",
        "tier": "CIRCUIT",
        "action": "append",
        "proposed_text": proposed,
        "evidence": adj.get('evidence', '')[:300],
        "weight": adj.get('weight', 0.85),
        "instruction_format": "agents_gate_row",
        "gate_name": gname,
    }


def build_memory_section_proposal(adj: dict, target: str, today: str) -> dict:
    """MEMORY.md edits: § Concept (wt:X.XX) — actionable one-liner with fix."""
    name = adj.get('kind', 'reflection').replace('_', '-')[:30]
    instruction = adj.get('evidence', 'fix the root cause')[:200] or 'fix the root cause'
    proposed = (
        f"\n§ {name} (wt:{adj.get('weight', 0.65):.2f}) — {instruction}. "
        f"Source: {today} ADAPT cycle on {target}."
    )
    return {
        "file": "MEMORY.md",
        "tier": "MEMORY",
        "action": "append",
        "proposed_text": proposed,
        "evidence": adj.get('evidence', '')[:300],
        "weight": adj.get('weight', 0.65),
        "instruction_format": "memory_section",
    }


def build_identity_proposal(adj: dict, target: str, today: str) -> dict:
    """IDENTITY.md edits: Evolution Log table row, like SOUL.md."""
    instruction = adj.get('evidence', '')[:200] or 'identity-state update'
    proposed = (
        f"\n| {today} | {adj.get('kind','reflection')}-identity (wt:{adj.get('weight',0.85):.2f}) | "
        f"Update identity self-model: {instruction[:180]} |"
    )
    return {
        "file": "IDENTITY.md",
        "tier": "CIRCUIT",
        "action": "append",
        "proposed_text": proposed,
        "evidence": adj.get('evidence', '')[:300],
        "weight": adj.get('weight', 0.85),
        "instruction_format": "identity_evolution_log_row",
    }


# ─────────────────────────────────────────────────────────────────────
# INTERPRETIVE ADAPT: infer instructions from role-behavior gap
# ─────────────────────────────────────────────────────────────────────

def extract_agent_role(doctrine: str) -> str:
    """Pull the agent's stated role from its doctrine. The role is a short
    declarative statement of what the agent IS (not what it does or believes)."""
    soul = doctrine[:2500]
    # Look for soul-opener-like lines (skip frontmatter, headers, lists)
    in_frontmatter = False
    in_code = False
    fm_done = False
    for line in soul.splitlines():
        if not fm_done:
            if line.strip() == '---':
                if in_frontmatter:
                    fm_done = True
                else:
                    in_frontmatter = True
                continue
            if in_frontmatter:
                continue
        if line.strip().startswith('```'):
            in_code = not in_code
            continue
        if in_code:
            continue
        s = line.strip()
        if not s or s.startswith('#') or s.startswith('|') or s.startswith('-') or s.startswith('*') or s.startswith('§'):
            continue
        # First prose statement is the role
        if 20 < len(s) < 250:
            return s
    return "agent with undefined role"


def extract_session_voice(sessions: list) -> dict:
    """From the most recent session(s), extract what the agent is actually doing.

    Returns {first_user_msg, last_msg_preview, message_count, role_counts, platform, model, intent_keywords}
    intent_keywords are extracted from first_user_msg: words that signal domain (plugin, research, code, etc.)
    """
    if not sessions:
        return {}
    # Use top 3 most recent non-corrupt sessions
    recent = [s for s in sessions[:5] if not s.get('corrupted')]
    if not recent:
        return {}
    combined_first = ' | '.join(s.get('first_user_msg', '') for s in recent if s.get('first_user_msg'))
    combined_last = ' | '.join(s.get('last_msg_preview', '') for s in recent if s.get('last_msg_preview'))
    # Extract intent keywords (long words that aren't stopwords)
    stopwords = {'this', 'that', 'with', 'from', 'have', 'been', 'will', 'they', 'them',
                 'were', 'said', 'each', 'which', 'their', 'there', 'would', 'about',
                 'because', 'session', 'started', 'since', 'were', 'working'}
    import re as _re
    words = _re.findall(r'\b[A-Za-z][A-Za-z0-9-]{4,}\b', combined_first + ' ' + combined_last)
    keywords = []
    for w in words:
        wl = w.lower()
        if wl not in stopwords and wl not in [k.lower() for k in keywords]:
            keywords.append(w)
        if len(keywords) >= 8:
            break
    return {
        'first_user_msgs': combined_first[:600],
        'last_msg_previews': combined_last[:400],
        'message_count': sum(s.get('message_count', 0) for s in recent),
        'platform': recent[0].get('platform', ''),
        'model': recent[0].get('model', ''),
        'intent_keywords': keywords,
    }


def group_failures_by_kind(anomalies: list, patterns: list) -> dict:
    """Group reflect findings by *failure mode*, not by name.

    A failure mode is what the agent COULDN'T DO. Different pattern names that
    describe the same missing capability should cluster together.
    """
    groups = {
        'apply_proposals': [],
        'sync_identity': [],
        'delegate_correctly': [],
        'stay_in_role': [],
        'execute_healing': [],
        'detect_without_resolution': [],
        'context_preservation': [],
        'memory_consistency': [],
        'session_continuity': [],
        'other': [],
    }
    for a in anomalies:
        al = a.lower()
        if 'proposal' in al and ('appli' in al or 'disconnect' in al or 'impotence' in al):
            groups['apply_proposals'].append(a)
        elif 'identity' in al and ('sync' in al or 'desync' in al or 'reflect_count' in al or 'paradox' in al or 'orphaned' in al or 'decay' in al):
            groups['sync_identity'].append(a)
        elif 'deleg' in al or 'ban' in al or 'execution' in al:
            groups['delegate_correctly'].append(a)
        elif 'role' in al or 'wall' in al or 'bridge' in al or 'hands' in al:
            groups['stay_in_role'].append(a)
        elif 'heal' in al or 'resolution' in al or 'resolv' in al:
            groups['execute_healing'].append(a)
        elif 'detect' in al or 'cross_cycle' in al or 'accumulation' in al:
            groups['detect_without_resolution'].append(a)
        elif 'context' in al:
            groups['context_preservation'].append(a)
        elif 'memory' in al or 'frozen' in al or 'stale' in al:
            groups['memory_consistency'].append(a)
        elif 'session' in al or 'continuity' in al:
            groups['session_continuity'].append(a)
        else:
            groups['other'].append(a)
    # Drop empty groups
    return {k: v for k, v in groups.items() if v}


def interpret_role_behavior_gap(absorb: dict, reflect: dict, target: str) -> list:
    """INTERPRETIVE ADAPT: read the agent's role + behavior and infer what instructions
    would make the agent better at the gap between them.

    Returns a list of {file, action, proposed_text, evidence, weight, instruction_format,
                       gap_kind, role, behavior, grounding} dicts.

    This is NOT pattern translation. This is reasoning about what the agent needs.
    """
    circuit = absorb.get('circuit_files', {}) or {}
    soul_text = (circuit.get('SOUL.md') or {}).get('content', '') or ''
    identity_text = (circuit.get('IDENTITY.md') or {}).get('content', '') or ''
    role = extract_agent_role(soul_text)
    sessions = absorb.get('sessions', []) or []
    voice = extract_session_voice(sessions)
    intent_keywords = voice.get('intent_keywords', [])
    failures = group_failures_by_kind(
        reflect.get('anomalies', []) or [],
        reflect.get('patterns', []) or [],
    )
    proposals = []

    today = datetime.now().strftime('%Y-%m-%d')
    today_compact = datetime.now().strftime('%Y-%m-%d %H:%M')

    grounding = f"role='{role[:60]}', recent work={','.join(intent_keywords[:5])}, " \
                f"platform={voice.get('platform','?')}, model={voice.get('model','?')}"

    # GATE PROPOSALS: behavioral reflexes with When/Action shape
    # SOUL PROPOSALS: behavioral rules with action

    # 1. apply_proposals failure → reflex that prevents accumulated orphan proposals
    if 'apply_proposals' in failures:
        if any('plugin' in kw.lower() or 'telegram' in kw.lower() for kw in intent_keywords):
            # Domain-specific: write to AGENTS.md as gate
            proposed = (
                f"\n| **G-APPLY-OR-QUEUE** | **When** any insight contains 'proposal' or any kanban task is generated "
                f"(especially during {','.join(intent_keywords[:2])} work) | **Action** within 1 turn: either (a) verify the "
                f"proposal/tasks applied, or (b) write to PROPOSALS-QUEUED.md with cycle_id and reason. Do not let "
                f"proposed-but-not-applied entries accumulate in Evolution Log. "
                f"(Gap: apply_proposals; role={role[:40]}; work={','.join(intent_keywords[:3])}) |"
            )
            proposals.append({
                "file": "AGENTS.md",
                "tier": "CIRCUIT",
                "action": "append",
                "proposed_text": proposed,
                "evidence": f"Recurring anomaly: proposals-applied-disconnect. Found in: {failures['apply_proposals'][:2]}",
                "weight": 0.92,
                "instruction_format": "agents_gate_row",
                "gate_name": "G-APPLY-OR-QUEUE",
                "gap_kind": "apply_proposals",
                "role": role,
                "grounding": grounding,
            })
        else:
            proposed = (
                f"\n| **G-APPLY-OR-QUEUE** | **When** any insight contains 'proposal' | **Action** within 1 turn: either "
                f"verify application or write to PROPOSALS-QUEUED.md. Do not accumulate orphan proposals. |"
            )
            proposals.append({
                "file": "AGENTS.md", "tier": "CIRCUIT", "action": "append",
                "proposed_text": proposed,
                "evidence": f"apply_proposals anomaly: {failures['apply_proposals'][:2]}",
                "weight": 0.85, "instruction_format": "agents_gate_row",
                "gate_name": "G-APPLY-OR-QUEUE", "gap_kind": "apply_proposals",
                "role": role, "grounding": grounding,
            })

    # 2. sync_identity failure → reflex that catches desync on session start
    if 'sync_identity' in failures:
        proposed = (
            f"\n| {today} | identity-sync-reflex (wt:0.95) | "
            f"At session start, read IDENTITY.md reflect_count vs SOUL.md/AGENTS.md frontmatter. "
            f"If they differ, write a sync entry to MEMORY.md as the FIRST output. The drift accumulates silently "
            f"otherwise. (Gap: sync_identity; role={role[:50]}) |"
        )
        proposals.append({
            "file": "SOUL.md", "tier": "CIRCUIT", "action": "append",
            "proposed_text": proposed,
            "evidence": f"sync_identity anomaly: {failures['sync_identity'][:2]}",
            "weight": 0.95, "instruction_format": "soul_evolution_log_row",
            "gap_kind": "sync_identity", "role": role, "grounding": grounding,
        })

    # 3. stay_in_role failure → reflex that prevents bridge→hands drift
    if 'stay_in_role' in failures:
        proposed = (
            f"\n| **G-BRIDGE-NOT-WALL** | **When** telegram session goes 100+ messages deep on a single "
            f"technical issue (e.g., {','.join(intent_keywords[:2]) or 'code/plugin'}) | **Action** at message 100, "
            f"check whether the issue requires delegation. If so, write kanban task and step out. Do not stay in the "
            f"conversation after delegation. Identity = {role[:60]}. |"
        )
        proposals.append({
            "file": "AGENTS.md", "tier": "CIRCUIT", "action": "append",
            "proposed_text": proposed,
            "evidence": f"stay_in_role anomaly: {failures['stay_in_role'][:2]}",
            "weight": 0.90, "instruction_format": "agents_gate_row",
            "gate_name": "G-BRIDGE-NOT-WALL", "gap_kind": "stay_in_role",
            "role": role, "grounding": grounding,
        })

    # 4. context_preservation failure → reflex that protects the golden rule
    if 'context_preservation' in failures:
        proposed = (
            f"\n| {today} | context-protection-reset (wt:0.85) | "
            f"When context usage > 70%, immediately write a session checkpoint to .session-checkpoint.md "
            f"and pause active work. Do not let context exhaustion interrupt {role[:40]}'s role mid-task. "
            f"Resume from checkpoint, not from scratch. |"
        )
        proposals.append({
            "file": "SOUL.md", "tier": "CIRCUIT", "action": "append",
            "proposed_text": proposed,
            "evidence": f"context_preservation anomaly: {failures['context_preservation'][:2]}",
            "weight": 0.85, "instruction_format": "soul_evolution_log_row",
            "gap_kind": "context_preservation", "role": role, "grounding": grounding,
        })

    # 5. memory_consistency failure → reflex that prevents frozen-memory drift
    if 'memory_consistency' in failures:
        proposed = (
            f"\n| {today} | memory-staleness-watch (wt:0.85) | "
            f"At every cycle start, check the last MEMORY.md entry date. If > 7 days stale, "
            f"append a recovery entry BEFORE any other write. The {len(failures.get('memory_consistency',[]))} "
            f"stale-memory findings in history would not have happened with this gate. |"
        )
        proposals.append({
            "file": "SOUL.md", "tier": "CIRCUIT", "action": "append",
            "proposed_text": proposed,
            "evidence": f"memory_consistency anomaly: {failures['memory_consistency'][:2]}",
            "weight": 0.85, "instruction_format": "soul_evolution_log_row",
            "gap_kind": "memory_consistency", "role": role, "grounding": grounding,
        })

    # 6. session_continuity failure → reflex that prevents loss-of-context across sessions
    if 'session_continuity' in failures:
        proposed = (
            f"\n| {today} | session-resume-gate (wt:0.80) | "
            f"When starting a new session after another {target} session, read .session-checkpoint.md "
            f"first. Do not start fresh; the prior session's working state is the starting point. "
            f"This is what makes sessions cumulative rather than disposable. |"
        )
        proposals.append({
            "file": "SOUL.md", "tier": "CIRCUIT", "action": "append",
            "proposed_text": proposed,
            "evidence": f"session_continuity anomaly: {failures['session_continuity'][:2]}",
            "weight": 0.80, "instruction_format": "soul_evolution_log_row",
            "gap_kind": "session_continuity", "role": role, "grounding": grounding,
        })

    # 7. THE META-INSIGHT: ground express in session, not doctrine
    # This is the principle I (EVOL) discovered while running the cycle. The agent's express phase
    # is contaminated because it reads doctrine but should read session content.
    if voice.get('first_user_msgs'):
        proposed = (
            f"\n| {today} | express-grounded-in-session (wt:0.95) | "
            f"When expressing the agent's POV (e.g., during EVOL express phase or self-review), ground the opinion "
            f"in the most recent session's first_user_msg and last_msg_preview, not just the doctrine opener. "
            f"The doctrine says what the agent believes; the session shows what the agent is doing. "
            f"Recent work: {voice.get('first_user_msgs','')[:80]}. |"
        )
        proposals.append({
            "file": "SOUL.md", "tier": "CIRCUIT", "action": "append",
            "proposed_text": proposed,
            "evidence": f"express-raw-output-repeated anomaly + EVOL cycle contamination observed "
                       f"({today_compact}). Work anchor: {voice.get('first_user_msgs','')[:60]}",
            "weight": 0.95, "instruction_format": "soul_evolution_log_row",
            "gap_kind": "express_contamination", "role": role, "grounding": grounding,
        })

    return proposals


def interpret_targeted_instructions(absorb: dict, reflect: dict, target: str) -> list:
    """Interpret: given this agent's role and what it's actually working on,
    what 1-3 specific instructions would make it better at the work in front of it?

    This is the 'what would the agent need next session to do' pass. It reads
    recent session content and proposes instructions anchored in the actual
    work, not in the failure taxonomy.
    """
    circuit = absorb.get('circuit_files', {}) or {}
    soul_text = (circuit.get('SOUL.md') or {}).get('content', '') or ''
    role = extract_agent_role(soul_text)
    sessions = absorb.get('sessions', []) or []
    voice = extract_session_voice(sessions)
    if not voice:
        return []
    first_msgs = voice.get('first_user_msgs', '')
    last_msgs = voice.get('last_msg_previews', '')
    intent_keywords = voice.get('intent_keywords', [])
    if not intent_keywords:
        return []
    today = datetime.now().strftime('%Y-%m-%d')
    grounding = f"role='{role[:50]}', keywords={intent_keywords[:6]}"
    out = []

    # If the recent work is about plugins/architecture, propose an instruction
    # about THAT work — not about cycle meta-failures
    plugin_kws = [k for k in intent_keywords if any(s in k.lower() for s in ('plugin', 'multiplex', 'gateway', 'config'))]
    research_kws = [k for k in intent_keywords if any(s in k.lower() for s in ('research', 'arxiv', 'paper', 'web', 'search'))]
    code_kws = [k for k in intent_keywords if any(s in k.lower() for s in ('code', 'repo', 'pr', 'fix', 'bug'))]

    if plugin_kws:
        proposed = (
            f"\n§ {target}-work-anchor (wt:0.85) — "
            f"Recent session work involved: {','.join(intent_keywords[:5])}. "
            f"When {target} starts its next session, first read .session-checkpoint.md or the most recent "
            f"kanban state to see where the {plugin_kws[0] if plugin_kws else 'plugin'} work left off. "
            f"Do not re-derive what was already discovered. (Gap: work-continuity; grounding: {grounding})"
        )
        out.append({
            "file": "MEMORY.md", "tier": "MEMORY", "action": "append",
            "proposed_text": proposed,
            "evidence": f"Recent session: '{first_msgs[:200]}'",
            "weight": 0.85, "instruction_format": "memory_section",
            "gap_kind": "work_continuity", "role": role, "grounding": grounding,
        })
    elif code_kws:
        proposed = (
            f"\n§ {target}-work-anchor (wt:0.85) — "
            f"Recent session work involved: {','.join(intent_keywords[:5])}. "
            f"Next session should resume from the {code_kws[0]} thread, not start over. "
            f"(Grounding: {grounding})"
        )
        out.append({
            "file": "MEMORY.md", "tier": "MEMORY", "action": "append",
            "proposed_text": proposed,
            "evidence": f"Recent session: '{first_msgs[:200]}'",
            "weight": 0.85, "instruction_format": "memory_section",
            "gap_kind": "work_continuity", "role": role, "grounding": grounding,
        })
    elif research_kws:
        proposed = (
            f"\n§ {target}-work-anchor (wt:0.85) — "
            f"Recent session work involved: {','.join(intent_keywords[:5])}. "
            f"Next session should resume from the {research_kws[0]} thread, with prior findings in mind. "
            f"(Grounding: {grounding})"
        )
        out.append({
            "file": "MEMORY.md", "tier": "MEMORY", "action": "append",
            "proposed_text": proposed,
            "evidence": f"Recent session: '{first_msgs[:200]}'",
            "weight": 0.85, "instruction_format": "memory_section",
            "gap_kind": "work_continuity", "role": role, "grounding": grounding,
        })
    return out


def build_cleanup_proposal(target: str, profile) -> dict:
    """Scan all circuit files for garbage: line-level spam + multi-line malformed rows."""
    from _lib import find_garbage_rows_in_text
    garbage_lines = {'SOUL.md': [], 'AGENTS.md': [], 'IDENTITY.md': [], 'MEMORY.md': []}
    multiline_rows = {}
    for f in ['SOUL.md', 'AGENTS.md', 'IDENTITY.md', 'MEMORY.md']:
        path = profile / f
        if not path.exists():
            continue
        text = path.read_text(errors='replace')
        for i, line in enumerate(text.splitlines(), 1):
            if is_garbage_line(line):
                garbage_lines[f].append(i)
        rows = find_garbage_rows_in_text(text)
        if rows:
            multiline_rows[f] = rows
    total_lines = sum(len(v) for v in garbage_lines.values())
    total_multiline = sum(len(v) for v in multiline_rows.values())
    total = total_lines + total_multiline
    if total == 0:
        return {"action": "none", "reason": "no_garbage_detected"}
    return {
        "file": "ALL",
        "tier": "KNOWLEDGE",
        "action": "cleanup",
        "proposed_text": "",
        "evidence": f"Garbage: {total_lines} line-level, {total_multiline} multi-line rows across circuit files",
        "weight": 0.95,
        "instruction_format": "garbage_strip",
        "garbage_lines": garbage_lines,
        "multiline_rows": multiline_rows,
        "garbage_count": total,
    }


def build_demotion_proposal(adj: dict, target: str, profile) -> dict:
    """Demote a recurring pattern from circuit to knowledge."""
    name = adj.get('kind', 'unknown-pattern')
    proposed_text = (
        f"\n§ demoted-{name} (wt:0.30) — was promoted to circuit but recurred without "
        f"resolution; demoted to knowledge tier. Evidence: {adj.get('evidence','')[:150]}"
    )
    return {
        "file": "MEMORY.md",
        "tier": "KNOWLEDGE",
        "action": "append_demotion_marker",
        "proposed_text": proposed_text,
        "evidence": adj.get('evidence', '')[:300],
        "weight": 0.30,
        "instruction_format": "memory_section",
        "demoted_from": "CIRCUIT",
    }


def build_temporal_drift_proposal(temporal: dict, target: str) -> dict:
    """Propose updating IDENTITY.md frontmatter to reflect actual reflect_count.

    Detected when IDENTITY.md claims reflect_count=N but recent session system_prompts
    show reflect_count=M where M >> N. The drift means N cycles happened that the
    file doesn't know about. The fix is to:
    1. Update IDENTITY.md frontmatter: last_reflect to today, reflect_count to max(current, session_count)
    2. Append a self-activation entry to the Evolution Log
    """
    if not temporal or temporal.get('drift') is None:
        return {"action": "none", "reason": "no_drift"}
    drift = temporal.get('drift', 0)
    if drift <= 0:
        return {"action": "none", "reason": "no_drift_to_heal"}
    current = temporal.get('current', {})
    series = temporal.get('series', [])
    if not current or not series:
        return {"action": "none", "reason": "no_temporal_data"}
    actual_count = max(current.get('reflect_count', 0), series[-1].get('reflect_count', 0))
    today = datetime.now().strftime('%Y-%m-%d')
    # The fix: update IDENTITY.md frontmatter to match reality
    proposed_replacement = (
        f"---\nrole: {current.get('role', target)}\n"
        f"last_reflect: {today}\nreflect_count: {actual_count}\n---"
    )
    return {
        "file": "IDENTITY.md",
        "tier": "CIRCUIT",
        "action": "replace",
        "current_excerpt": f"---\nrole: {current.get('role', target)}\nlast_reflect: {current.get('last_reflect', '')}\nreflect_count: {current.get('reflect_count', 0)}\n---",
        "proposed_text": proposed_replacement,
        "evidence": f"Drift detected: IDENTITY.md says reflect_count={current.get('reflect_count', 0)}, "
                    f"but most recent session's system_prompt says reflect_count={series[-1].get('reflect_count', 0)}. "
                    f"Drift of {drift} cycles unaccounted for.",
        "weight": 0.95,
        "instruction_format": "identity_frontmatter_replacement",
        "drift_magnitude": drift,
    }


def propose_for_adjustment(adj: dict, target: str, profile, today: str, session_signal: dict = None) -> dict:
    kind = adj.get('kind', '')
    weight = adj.get('weight', 0.5)
    tier = classify_tier(weight)

    if tier == 'CIRCUIT' and weight >= 0.85:
        # Default: write to AGENTS.md as a gate, SOUL.md as evolution log
        if kind in ('stale_doctrine', 'recurring_orphan'):
            return build_agents_gate_proposal(adj, target, today, session_signal)
        return build_soul_proposal(adj, target, today, session_signal)
    elif tier == 'MEMORY':
        return build_memory_section_proposal(adj, target, today)
    elif tier == 'decay':
        return {"action": "none", "reason": "below_decay_threshold"}
    else:
        return build_memory_section_proposal(adj, target, today)


def apply_conflict_rules(plan: list, express: dict, explore: dict) -> list:
    """If the agent's voice and external evidence both contradict a reflect finding,
    demote it. If they confirm it, keep it. Otherwise, leave as-is."""
    opinion = (express.get('opinion') or '').lower()
    external_text = ' '.join(e.get('snippet', '').lower() + e.get('title', '').lower()
                             for e in explore.get('external', []))
    for p in plan:
        if p.get('action') not in ('append', 'cleanup'):
            continue
        ev = (p.get('evidence') or '').lower()
        if not ev:
            continue
        # Crude contradiction heuristic: if opinion says "fine" or "correct" but finding says "wrong"
        opinion_disagrees = ('fine' in opinion or 'correct' in opinion or 'not stale' in opinion) and ('stale' in ev or 'wrong' in ev or 'broken' in ev)
        external_disagrees = 'no evidence' in external_text and ('stale' in ev or 'broken' in ev)
        if opinion_disagrees and external_disagrees:
            p['action'] = 'demote_to_knowledge'
            p['demotion_reason'] = 'agent + external both contradict reflect finding'
        elif opinion_disagrees or external_disagrees:
            p['action'] = 'none'
            p['skip_reason'] = 'partial contradiction — escalate'
    return plan


def dedupe(plan: list, profile) -> list:
    """Drop proposals whose proposed_text already exists in target file."""
    out = []
    for p in plan:
        if p.get('action') in ('append', 'append_demotion_marker') and p.get('proposed_text'):
            if file_contains(profile.name, p['file'], p['proposed_text'].strip()):
                p['action'] = 'none'
                p['skip_reason'] = 'already_exists'
        out.append(p)
    return out


# ─────────────────────────────────────────────────────────────────────
# INSTRUCTION EFFECT ANALYSIS
# For every new instruction, check whether it:
# - adds new behavior (additive)
# - conflicts with an existing instruction (must remove the old)
# - supersedes an existing instruction (replace)
# - merges with an existing instruction (consolidate)
# - contradicts an existing instruction without removing it (escalate)
# ─────────────────────────────────────────────────────────────────────

def _extract_actionable_lines(file_text: str) -> list:
    """Pull all behavioral-rule lines from a circuit file. These are the lines
    that an agent might follow as instructions, so a new instruction must be
    compared against them.

    Returns list of {line_num, file, kind, text, keywords} for:
    - table rows in Evolution Log
    - gate rows in Gates section
    - § sections in MEMORY
    """
    out = []
    if not file_text:
        return out
    for i, line in enumerate(file_text.splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        kind = None
        if s.startswith('§ '):
            kind = 'memory_section'
        elif s.startswith('| **G-'):
            kind = 'gate_row'
        elif s.startswith('| ') and '(wt:' in s:
            kind = 'evolution_log_row'
        if kind:
            # Extract key content (after weight, before final |)
            keywords = re.findall(r'[A-Za-z][A-Za-z0-9-]{4,}', s)
            out.append({'line_num': i, 'kind': kind, 'text': s, 'keywords': [k.lower() for k in keywords]})
    return out


def _keywords_of(text: str) -> set:
    """Extract significant keywords from a piece of text for overlap comparison."""
    if not text:
        return set()
    stopwords = {'this', 'that', 'with', 'from', 'have', 'been', 'will', 'they', 'them',
                 'were', 'said', 'each', 'which', 'their', 'there', 'would', 'about',
                 'because', 'session', 'started', 'since', 'working', 'when', 'then',
                 'after', 'before', 'should', 'could', 'would', 'every', 'always'}
    words = re.findall(r'[A-Za-z][A-Za-z0-9-]{4,}', text)
    return {w.lower() for w in words if w.lower() not in stopwords}


def _intent_of(line: dict) -> str:
    """Extract the *intent* of a circuit-file line in 1-2 phrases.

    For evolution_log_row: '{kind}-rule: {action}' or similar
    For gate_row: '{gname}: when {when} do {action}'
    For memory_section: '{name}: {definition}'
    """
    text = line.get('text', '')
    kind = line.get('kind', '')
    if kind == 'gate_row':
        # | **G-NAME** | **When** X | **Action** Y |
        m = re.search(r'\*\*([\w-]+)\*\*.*?When\s+(.+?)\s*\|\s*\*?\*?Action\*?\*?\s+(.+?)(?:\s*\|)?$', text)
        if m:
            return f"gate:{m.group(1)} when={m.group(2)[:60]} action={m.group(3)[:80]}"
    if kind == 'memory_section':
        m = re.search(r'§\s+([\w-]+).*?—\s*(.+)', text)
        if m:
            return f"section:{m.group(1)} def={m.group(2)[:100]}"
    if kind == 'evolution_log_row':
        # | date | kind-rule (wt:0.XX) | instruction |
        parts = text.split('|')
        if len(parts) >= 4:
            return f"rule:{parts[2].strip()[:40]} instr={parts[3].strip()[:100]}"
    return text[:120]


def analyze_instruction_effect(proposed_text: str, file_rel: str, circuit_files: dict) -> dict:
    """For a proposed instruction, determine its net effect on existing circuit content.

    Returns:
      effect: 'additive' | 'merge_with' | 'supersedes' | 'conflicts' | 'contradicts'
      related_lines: [{file, line_num, kind, intent, overlap_score}]
      recommended_action: 'append' | 'replace' | 'remove_old' | 'merge_into' | 'escalate'
      reasoning: str (why this effect was chosen)
    """
    existing = _extract_actionable_lines(circuit_files.get(file_rel, {}).get('content', ''))
    proposed_kws = _keywords_of(proposed_text)
    if not proposed_kws:
        return {'effect': 'additive', 'related_lines': [], 'recommended_action': 'append',
                'reasoning': 'no keywords to compare; treat as additive'}

    # Score each existing line by keyword overlap
    scored = []
    for line in existing:
        existing_kws = set(line.get('keywords', []))
        overlap = len(proposed_kws & existing_kws)
        union = len(proposed_kws | existing_kws)
        score = overlap / union if union else 0
        if score >= 0.10:  # at least 10% overlap
            scored.append({'line_num': line['line_num'],
                           'file': file_rel,
                           'kind': line['kind'],
                           'intent': _intent_of(line),
                           'overlap_score': round(score, 3),
                           'overlap_keywords': sorted(list(proposed_kws & set(line.get('keywords', []))))[:8]})
    scored.sort(key=lambda x: -x['overlap_score'])

    if not scored:
        return {'effect': 'additive', 'related_lines': [], 'recommended_action': 'append',
                'reasoning': f'no existing lines share keywords with the proposal (proposed has {len(proposed_kws)} keywords)'}

    top = scored[0]
    if top['overlap_score'] >= 0.5:
        # Strong overlap: probably the new instruction is about the same thing
        # Need to determine if it adds, merges, or supersedes
        return {
            'effect': 'merge_with',
            'related_lines': scored[:3],
            'recommended_action': 'merge_into',
            'reasoning': f"high overlap ({top['overlap_score']:.2f}) with line {top['line_num']}; "
                         f"new instruction is about the same topic. Recommend merge to consolidate.",
            'merge_target_line': top['line_num'],
        }
    if top['overlap_score'] >= 0.25:
        # Moderate overlap: could be additive (new facet) or superseding (refinement)
        return {
            'effect': 'supersedes',
            'related_lines': scored[:3],
            'recommended_action': 'replace',
            'reasoning': f"moderate overlap ({top['overlap_score']:.2f}) with line {top['line_num']}; "
                         f"new instruction is a refinement. Recommend replacing the old with the new.",
            'supersede_target_line': top['line_num'],
        }
    if top['overlap_score'] >= 0.10:
        # Low but non-trivial overlap: probably additive but worth noting
        return {
            'effect': 'additive_related',
            'related_lines': scored[:3],
            'recommended_action': 'append',
            'reasoning': f"low overlap ({top['overlap_score']:.2f}) with line {top['line_num']}; "
                         f"new instruction is in the same neighborhood but addresses a different facet.",
        }
    return {'effect': 'additive', 'related_lines': [], 'recommended_action': 'append',
            'reasoning': 'no significant overlap'}


def apply_effect_to_proposal(proposal: dict, effect: dict) -> dict:
    """If the effect analysis recommends 'merge_with' or 'supersedes' or 'remove_old',
    convert the proposal's action and add a follow-up entry for the old line.

    Returns the updated proposal dict.
    """
    action = effect.get('recommended_action', 'append')
    if action == 'append':
        proposal['effect'] = effect.get('effect', 'additive')
        proposal['effect_reasoning'] = effect.get('reasoning', '')
        proposal['related_lines'] = effect.get('related_lines', [])
        return proposal

    if action == 'merge_into':
        # Add a follow-up: mark the old line as merged (insert a comment, or skip in next cycle)
        proposal['effect'] = 'merge_with'
        proposal['effect_reasoning'] = effect.get('reasoning', '')
        proposal['related_lines'] = effect.get('related_lines', [])
        proposal['merge_target_line'] = effect.get('merge_target_line')
        # Keep the append but mark the file with both append and a deprecation marker
        proposal['_followup'] = {
            'action': 'deprecate_line',
            'file': proposal['file'],
            'line': effect.get('merge_target_line'),
            'reason': f'merged into new instruction (overlap {effect["related_lines"][0]["overlap_score"]:.2f})',
        }
        return proposal

    if action == 'replace':
        # The proposal needs to become a replace, not append. Build the current_excerpt
        # from the related line's intent.
        related = effect.get('related_lines', [{}])[0]
        proposal['effect'] = 'supersedes'
        proposal['effect_reasoning'] = effect.get('reasoning', '')
        proposal['related_lines'] = effect.get('related_lines', [])
        proposal['supersede_target_line'] = effect.get('supersede_target_line')
        proposal['action'] = 'replace'
        # Try to find the exact current_excerpt by re-reading the file
        proposal['action_reason'] = f"supersedes line {related.get('line_num')} (overlap {related.get('overlap_score')})"
        return proposal

    if action == 'remove_old':
        proposal['effect'] = 'conflicts'
        proposal['effect_reasoning'] = effect.get('reasoning', '')
        proposal['related_lines'] = effect.get('related_lines', [])
        proposal['_followup'] = {
            'action': 'remove_line',
            'file': proposal['file'],
            'line': effect.get('related_lines', [{}])[0].get('line_num'),
            'reason': 'conflicts with new instruction',
        }
        return proposal

    return proposal


# ─────────────────────────────────────────────────────────────────────
# SELF-CHECK QUESTIONS
# At the end of ADAPT, EVOL must answer these to prove it interpreted intelligently.
# ─────────────────────────────────────────────────────────────────────

SELF_CHECK_QUESTIONS = [
    ("role_understanding", "What is this agent's role, in one sentence, from their doctrine? (not from the cycle's POV)"),
    ("behavior_understanding", "What was this agent actually doing in the most recent session, in one phrase?"),
    ("gap_identification", "What is the gap between the agent's role and their behavior, in one sentence?"),
    ("instruction_intent", "For the highest-weight proposal: what should the agent DO differently next session as a result of this instruction?"),
    ("instruction_effect", "For each proposed instruction, does it (a) add new behavior, (b) merge with an existing instruction, (c) supersede an old instruction, or (d) conflict with an old instruction?"),
    ("removal_decisions", "Are there any existing instructions that should be REMOVED because they are now obsolete or contradicted by the new state? If so, which?"),
    ("merge_decisions", "Are there any existing instructions that should be MERGED with the new ones to consolidate? If so, which?"),
    ("file_targeting", "Did you write to the correct file (SOUL.md for doctrine, AGENTS.md for gates, MEMORY.md for working knowledge, IDENTITY.md for self-model)? Why this file and not another?"),
    ("recurrence_acknowledgment", "If a pattern has recurred >5x in historical data, did you add a recurrence annotation so the next cycle knows this isn't new?"),
    ("session_grounding", "Is the instruction anchored in actual session content (recent first_user_msg, last_msg_preview) or only in doctrine text? Show the anchor."),
    ("what_would_break", "If this instruction is added, what existing behavior of the agent might break or contradict?"),
    ("what_would_improve", "If this instruction is added, what specific failure mode (anomaly) does it prevent or heal?"),
]


def build_self_check_questions(interpretive_proposals: list, work_anchored: list,
                                absorb: dict, reflect: dict, target: str) -> list:
    """Build a list of {question_id, question, context, suggested_answer_hint} dicts
    that EVOL must answer to prove interpretation. Context provides the raw data
    needed to answer each question honestly.
    """
    circuit = absorb.get('circuit_files', {}) or {}
    soul_text = (circuit.get('SOUL.md') or {}).get('content', '') or ''
    role = extract_agent_role(soul_text)
    sessions = absorb.get('sessions', []) or []
    voice = extract_session_voice(sessions) if sessions else {}
    first_msg = voice.get('first_user_msgs', '')[:200] if voice else ''
    last_msg = voice.get('last_msg_previews', '')[:200] if voice else ''
    failures = group_failures_by_kind(reflect.get('anomalies', []) or [], reflect.get('patterns', []) or [])
    failures_summary = ', '.join(sorted(failures.keys()))

    out = [
        {'qid': 'role', 'q': SELF_CHECK_QUESTIONS[0][1],
         'context': f"agent role from doctrine: '{role[:200]}'",
         'must_answer': True},
        {'qid': 'behavior', 'q': SELF_CHECK_QUESTIONS[1][1],
         'context': f"most recent session: first='{first_msg}' last='{last_msg}'",
         'must_answer': True},
        {'qid': 'gap', 'q': SELF_CHECK_QUESTIONS[2][1],
         'context': f"role vs recent behavior; failures observed: {failures_summary}",
         'must_answer': True},
        {'qid': 'top_proposal_intent', 'q': SELF_CHECK_QUESTIONS[3][1],
         'context': f"highest-weight proposal gap_kind={interpretive_proposals[0].get('gap_kind','?') if interpretive_proposals else 'none'}",
         'must_answer': interpretive_proposals or work_anchored},
        {'qid': 'effects', 'q': SELF_CHECK_QUESTIONS[4][1],
         'context': f"{len(interpretive_proposals) + len(work_anchored)} proposals generated; "
                    f"each was analyzed for overlap with existing circuit content",
         'must_answer': interpretive_proposals or work_anchored},
        {'qid': 'removals', 'q': SELF_CHECK_QUESTIONS[5][1],
         'context': "scan existing evolution_log rows and gate rows for ones that are now obsolete",
         'must_answer': True},
        {'qid': 'merges', 'q': SELF_CHECK_QUESTIONS[6][1],
         'context': f"find pairs of (existing, proposed) with overlap_score >= 0.5 in the effect analysis",
         'must_answer': True},
        {'qid': 'file_routing', 'q': SELF_CHECK_QUESTIONS[7][1],
         'context': "SOUL.md = doctrine, AGENTS.md = gates, MEMORY.md = working knowledge, IDENTITY.md = self-model",
         'must_answer': True},
        {'qid': 'recurrence', 'q': SELF_CHECK_QUESTIONS[8][1],
         'context': f"patterns seen >= 5x: {[(p['name'], p['evidence_count']) for p in (reflect.get('patterns') or []) if p.get('evidence_count', 0) >= 5][:5]}",
         'must_answer': True},
        {'qid': 'session_anchor', 'q': SELF_CHECK_QUESTIONS[9][1],
         'context': f"recent session work: {first_msg[:200]}",
         'must_answer': True},
        {'qid': 'what_breaks', 'q': SELF_CHECK_QUESTIONS[10][1],
         'context': f"new instructions may contradict existing gates/rows in {target} circuit files",
         'must_answer': True},
        {'qid': 'what_heals', 'q': SELF_CHECK_QUESTIONS[11][1],
         'context': f"failure modes to address: {failures_summary}",
         'must_answer': True},
    ]
    return [q for q in out if q['must_answer']]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('absorb_json')
    ap.add_argument('reflect_json')
    ap.add_argument('express_json')
    ap.add_argument('explore_json')
    ap.add_argument('-o', '--output')
    args = ap.parse_args()

    absorb = safe_load(Path(args.absorb_json))
    reflect = safe_load(Path(args.reflect_json))
    express = safe_load(Path(args.express_json))
    explore = safe_load(Path(args.explore_json))
    if not all([absorb, reflect, express, explore]):
        print("ERROR: missing input(s)", file=sys.stderr)
        sys.exit(1)

    target = absorb.get('profile', 'unknown')
    try:
        profile = profile_dir(target)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    today = datetime.now().strftime('%Y-%m-%d')
    plan = []

    # 1. Cleanup proposal (always considered)
    cleanup = build_cleanup_proposal(target, profile)
    if cleanup.get('action') != 'none':
        plan.append(cleanup)

    # 2. INTERPRETIVE: role-behavior gap analysis
    # Read the agent's role from doctrine + their actual work from sessions + failures from reflect.
    # Propose instructions that CLOSE THE GAP between what the agent is supposed to be and
    # what it's actually doing. This is the primary ADAPT output.
    interpretive_proposals = interpret_role_behavior_gap(absorb, reflect, target)
    plan.extend(interpretive_proposals)

    # 2a. INTERPRETIVE: work-anchored instructions
    # Read what the agent is actually working on and propose instructions for the next session.
    work_anchored = interpret_targeted_instructions(absorb, reflect, target)
    plan.extend(work_anchored)

    # 3. DEDUPE adjustment_points first (collapse by (kind, file, line))
    raw_adjustments = reflect.get('adjustment_points', []) or []
    adjustments = dedupe_adjustment_points(raw_adjustments)

    # 3a. One proposal per (unique) adjustment_point, grounded in session content
    #    (these are the templated proposals — secondary, only if interpretive didn't cover it)
    for adj in adjustments:
        session_signal = derive_session_grounded_context(adj, absorb)
        p = propose_for_adjustment(adj, target, profile, today, session_signal)
        plan.append(p)

    # 3b. Temporal drift proposal (if IDENTITY.md is stale relative to sessions)
    temporal = absorb.get('temporal_doctrine', {})
    drift_proposal = build_temporal_drift_proposal(temporal, target)
    if drift_proposal.get('action') not in ('none', None):
        plan.append(drift_proposal)

    # 4. Apply conflict rules
    plan = apply_conflict_rules(plan, express, explore)

    # 4b. INSTRUCTION EFFECT ANALYSIS: for every interpretive proposal, check whether
    #     the new instruction adds, merges, supersedes, or conflicts with existing content.
    #     Convert proposals to merge/replace operations as needed, and generate
    #     follow-up entries for deprecation/removal of the old line.
    circuit = absorb.get('circuit_files', {}) or {}
    for p in plan:
        if p.get('action') in ('append', 'append_demotion_marker') and p.get('proposed_text'):
            effect = analyze_instruction_effect(p['proposed_text'], p.get('file', ''), circuit)
            apply_effect_to_proposal(p, effect)

    # 5. Dedupe
    plan = dedupe(plan, profile)

    # 5b. Process follow-ups (deprecate old lines when new instructions supersede them)
    for p in plan:
        if p.get('_followup') and p.get('action') in ('append', 'replace', 'append_demotion_marker'):
            # Add a follow-up entry to the plan: insert a "DEPRECATED" comment line
            # OR a replace that neutralizes the old line. Simplest: append a deprecation note
            # to the same file with the old line reference.
            followup = p['_followup']
            file_rel = followup.get('file', p.get('file', ''))
            old_line = followup.get('line', '?')
            reason = followup.get('reason', '')
            if file_rel:
                deprecation_note = (
                    f"\n<!-- DEPRECATED L{old_line} ({today}): {reason} -->\n"
                )
                p['_deprecation_note'] = deprecation_note

    # 6. Validate format for every actionable
    for p in plan:
        if p.get('action') in ('append', 'append_demotion_marker') and p.get('proposed_text'):
            ok, reason = validate_proposal_format(p['proposed_text'], p['file'])
            if not ok:
                p['action'] = 'none'
                p['skip_reason'] = f"format_invalid: {reason}"

    # 7. SELF-CHECK QUESTIONS — must be answered to prove interpretation
    self_check_questions = build_self_check_questions(
        interpretive_proposals, work_anchored, absorb, reflect, target
    )

    actionable = [p for p in plan if p.get('action') in ('append', 'cleanup', 'append_demotion_marker', 'demote_to_knowledge', 'replace')]
    skipped = [p for p in plan if p.get('action') == 'none']
    summary = (
        f"Target: {target}. {len(actionable)} actionable, {len(skipped)} skipped. "
        f"Cleanup: {cleanup.get('garbage_count', 0)} garbage lines. "
        f"Files affected: {sorted(set(p['file'] for p in actionable if p.get('file')))}. "
        f"Interpretive proposals: {len(interpretive_proposals)}. "
        f"Work-anchored: {len(work_anchored)}. "
        f"Self-check questions: {len(self_check_questions)}."
    )

    out = {
        'adapt_ts': __import__('time').time(),
        'target': target,
        'adjustment_plan': plan,
        'actionable': actionable,
        'skipped': skipped,
        'summary': summary,
        'interpretive_count': len(interpretive_proposals),
        'work_anchored_count': len(work_anchored),
        'self_check_questions': self_check_questions,
    }

    text = json.dumps(out, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(text)
    else:
        print(text)


if __name__ == '__main__':
    main()
