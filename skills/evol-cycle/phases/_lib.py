"""Shared helpers for the 6-phase evol cycle.

- path resolution (HERMES_CONFIG_DIR or ~ or HERMES_DATA)
- circuit format validation (the "Actionable Instruction Principle")
- tier classification (CIRCUIT / MEMORY / KNOWLEDGE / decay)
"""
import os
import re
from pathlib import Path


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


def profile_dir(agent: str) -> Path:
    p = profiles_root() / agent
    if not p.exists():
        raise FileNotFoundError(f"profile dir not found: {p}")
    return p


CIRCUIT_FILES = ['SOUL.md', 'AGENTS.md', 'MEMORY.md', 'IDENTITY.md']

# Tier rules (from evol-core skill, ratified)
TIER_THRESHOLDS = {
    'CIRCUIT': 0.85,    # SOUL/AGENTS/IDENTITY/MEMORY files (durable doctrine)
    'MEMORY': 0.65,     # MEMORY.md (working memory)
    'KNOWLEDGE': 0.35,  # Graphiti Tier 3 (searchable, not doctrine)
    'decay': 0.15,      # delete after 30 days grace
}


def classify_tier(weight: float) -> str:
    if weight >= TIER_THRESHOLDS['CIRCUIT']:
        return 'CIRCUIT'
    if weight >= TIER_THRESHOLDS['MEMORY']:
        return 'MEMORY'
    if weight >= TIER_THRESHOLDS['KNOWLEDGE']:
        return 'KNOWLEDGE'
    return 'decay'


# Format rules per file (from circuit-file-editing skill, Goran 2026-05-30 permanent)
FILE_FORMATS = {
    'SOUL.md': {
        'kind': 'evolution_log_row',
        'pattern': r'^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*.+\(wt:\d+\.\d{2}\)\s*\|\s*.+\s*\|\s*$',
        'description': 'Evolution Log table row: | YYYY-MM-DD | promotion (wt:X.XX) | source |',
    },
    'AGENTS.md': {
        'kind': 'gate_row',
        'pattern': r'^\|\s*\*\*G-[A-Z0-9_-]+\*\*\s*\|',
        'description': 'Gate table row: | **G-NAME** | When | Action |',
    },
    'IDENTITY.md': {
        'kind': 'evolution_log_row',
        'pattern': r'^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*.+\(wt:\d+\.\d{2}\)\s*\|\s*.+\s*\|\s*$',
        'description': 'Evolution Log table row: | YYYY-MM-DD | promotion (wt:X.XX) | source |',
    },
    'MEMORY.md': {
        'kind': 'memory_section',
        'pattern': r'^§\s+\S.+\(wt:\d+\.\d{2}\)\s*—\s*\S+',
        'description': '§ Concept (wt:X.XX) — actionable one-liner with fix',
    },
}


# Detect metadata-only entries (fail the Actionable Instruction Principle)
METADATA_ONLY_PATTERNS = [
    re.compile(r'^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*[\w-]+\s*\(wt:\d+\.\d{2}\)\s*\|\s*\|?\s*$'),
    re.compile(r'^\|\s*\*\*G-[\w-]+\*\*\s*\|\s*When.*Do\s*\|\s*[\w-]+\s*\|\s*$'),
    re.compile(r'^§\s+[\w-]+\s*\(wt:\d+\.\d{2}\)\s*—\s*\.?\s*$'),
]


def is_metadata_only(text: str) -> bool:
    """True if the entry is just a name-with-weight, no actionable content."""
    stripped = text.strip()
    if not stripped:
        return False
    return any(p.match(stripped) for p in METADATA_ONLY_PATTERNS)


def detect_format(file_rel: str) -> dict:
    """Return format spec for a circuit file. Default to MEMORY.md rules if unknown."""
    return FILE_FORMATS.get(file_rel, FILE_FORMATS['MEMORY.md'])


def validate_proposal_format(proposed_text: str, file_rel: str) -> tuple[bool, str]:
    """Returns (is_valid, reason). If not valid, the proposal MUST be rejected."""
    fmt = detect_format(file_rel)
    # Strip leading whitespace/newlines; check first non-empty line
    lines = [l for l in proposed_text.splitlines() if l.strip()]
    if not lines:
        return False, "empty proposal"
    if is_metadata_only(lines[0]):
        return False, f"metadata-only (fails Actionable Instruction Principle): {lines[0][:80]}"
    # Format check: the first content line should match the file's pattern, OR be a clear section header
    if fmt['kind'] == 'evolution_log_row' and not re.match(fmt['pattern'], lines[0]):
        # Allow section headers too
        if not lines[0].startswith('## ') and not lines[0].startswith('|'):
            return False, f"first line should be Evolution Log row or ## header: {lines[0][:80]}"
    if fmt['kind'] == 'gate_row' and not re.match(fmt['pattern'], lines[0]):
        if not lines[0].startswith('| **G-'):
            return False, f"AGENTS.md edits must be gate rows: {lines[0][:80]}"
    if fmt['kind'] == 'memory_section' and not re.match(fmt['pattern'], lines[0]):
        if not lines[0].startswith('§ '):
            return False, f"MEMORY.md edits must be § sections: {lines[0][:80]}"
    return True, "ok"


# Garbage detection: spam that should be stripped
GARBAGE_PATTERNS = [
    re.compile(r'^\s*\|\s*CROSS-CYCLE PATTERN\s*\(recurred\s+\d+x\):\s*[\w-]+\..*$'),
    re.compile(r'^\s*Auto-detected by MEMORIZE cross-cycle analyzer\.\s*$'),
    re.compile(r'^\s*\| [Yy]aml-style', re.IGNORECASE),
    re.compile(r'^\s*##\s*Evolution Log Entry\s*$'),
    # Meta-narrative rows: action column starts with "When X, then <evidence copy>"
    # These are reflect findings embedded in circuit edits instead of real instructions.
    re.compile(r'^\s*\|\s*\d{4}-\d{2}-\d{2}\s*\|[^|]+\|\s*When\s+[^,]+,\s+then\s+\S{50,}\s*\|'),
    # Rows that are just the reflect-evidence text dumped into the action column
    re.compile(r'^\s*\|\s*\d{4}-\d{2}-\d{2}\s*\|[^|]+\|\s*##\s+\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*\|'),
    # Empty promotion: timestamp + empty slug + weight + AUTO-APPLIED source
    re.compile(r'^\s*\|\s*\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[\d\+\-:.]*\s*\|\s+\(wt:[\d.]+\)\s*\|.*AUTO-APPLIED.*\|'),
    # Empty slug (just whitespace) in any column
    re.compile(r'^\s*\|\s*\d{4}[-/]\d{2}[-/]\d{2}[T\s][^|]*\|\s+\(wt:'),
]


def is_garbage_line(line: str) -> bool:
    return any(p.match(line) for p in GARBAGE_PATTERNS)


def find_garbage_rows_in_text(text: str) -> list:
    """Find malformed Evolution Log rows that span multiple lines.

    A real Evolution Log row fits on a single line and ends with `|`. Rows that
    span multiple lines (the action column contains a newline) are malformed and
    indicate a copy-paste-of-evidence failure. Returns the line numbers of the
    full row (1-indexed) so the whole multi-line row can be stripped.
    """
    lines = text.splitlines()
    garbage_rows = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # A row starts with `| YYYY-MM-DD |` (the date column)
        if not re.match(r'^\s*\|\s*\d{4}-\d{2}-\d{2}\s*\|', line):
            i += 1
            continue
        # Find the row's end. A real row ends on the same line with `| ... |`
        # A malformed row continues until we find a `|` at end of line.
        if line.rstrip().endswith('|'):
            i += 1
            continue
        # Multi-line row detected. Mark this line and all subsequent until terminator.
        start = i
        while i < len(lines) and not lines[i].rstrip().endswith('|'):
            i += 1
        # i now points to the terminator line. Include it.
        end = i  # inclusive
        garbage_rows.append((start + 1, end + 1))  # 1-indexed inclusive
        i += 1
    return garbage_rows


def strip_garbage_rows(path: Path) -> dict:
    """Remove multi-line garbage rows from a circuit file. Returns strip stats."""
    if not path.exists():
        return {"verified": False, "reason": "file_not_found"}
    before = path.read_text(errors='replace')
    sha_before = sha256(before)
    rows = find_garbage_rows_in_text(before)
    if not rows:
        return {"verified": False, "reason": "no_multiline_garbage"}
    lines = before.splitlines()
    keep = [l for i, l in enumerate(lines, 1)
            if not any(s <= i <= e for s, e in rows)]
    after = '\n'.join(keep)
    if not after.endswith('\n'):
        after += '\n'
    try:
        path.write_text(after)
    except Exception as e:
        return {"verified": False, "reason": f"write_failed: {e}"}
    sha_after = sha256(after)
    return {
        "verified": True,
        "delta_lines": after.count('\n') - before.count('\n'),
        "sha_before": sha_before,
        "sha_after": sha_after,
        "rows_stripped": len(rows),
        "rows": rows,
    }
