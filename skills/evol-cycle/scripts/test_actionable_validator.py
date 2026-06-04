#!/usr/bin/env python3
"""Self-test for the Actionable Instruction Principle validator.

Run after any change to _lib.validate_proposal_format, _lib.is_metadata_only,
or _lib.FILE_FORMATS. Prints PASS/FAIL per case and a summary.

Exit 0 = all pass. Exit 1 = at least one fail.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'phases'))
from _lib import validate_proposal_format  # noqa: E402


CASES = [
    # (description, proposed_text, file_rel, expected_valid, expected_substring_in_reason)
    # ===== SOUL/IDENTITY.md: Evolution Log table rows =====
    ("SOUL: real instruction row",
     "\n| 2026-06-04 | pending-question-rule (wt:0.90) | Read pending_questions.md at start of every cycle; if items > 24h old, dispatch or escalate |",
     "SOUL.md", True, ""),
    ("SOUL: metadata-only (name + weight, no instruction)",
     "\n| 2026-06-04 | unparsed-reflect (wt:0.90) | |",
     "SOUL.md", False, "metadata-only"),
    ("SOUL: section header is allowed",
     "\n## 2026-06-04 — Note\n\nThis is a section header followed by prose.",
     "SOUL.md", True, ""),
    ("SOUL: prose without header is rejected",
     "\nThis is just prose, not a row or header.",
     "SOUL.md", False, "Evolution Log row"),
    # ===== AGENTS.md: Gate table rows =====
    ("AGENTS: real gate row",
     "\n| **G-EVOL-PENDING-0915** | **When** pending_questions.md has items > 24h old | **Action** dispatch via kanban_create or escalate to Goran |",
     "AGENTS.md", True, ""),
    ("AGENTS: bare name, no When/Action",
     "\n| per-agent-evol | 6 patterns |",
     "AGENTS.md", False, "AGENTS.md edits must be gate"),
    # ===== MEMORY.md: § sections =====
    ("MEMORY: real § section",
     "\n§ memory-frozen-detection (wt:0.92) — When last MEMORY.md entry > 7 days stale, append recovery entry before any other propose.",
     "MEMORY.md", True, ""),
    ("MEMORY: metadata-only §",
     "\n§ unparsed-reflect (wt:0.90) |",
     "MEMORY.md", False, "metadata-only"),
    ("MEMORY: prose without § is rejected",
     "\nThis is just prose.",
     "MEMORY.md", False, "MEMORY.md edits must be"),
    # ===== Edge cases =====
    ("Empty proposal",
     "",
     "SOUL.md", False, "empty"),
    ("Whitespace-only proposal",
     "   \n\n  \n",
     "SOUL.md", False, "empty"),
    ("Unknown file falls back to MEMORY.md rules",
     "\n§ unknown-file-rule (wt:0.50) — when something happens, do something.",
     "FAKE.md", True, ""),
]


def main():
    passed = 0
    failed = 0
    for desc, text, file_rel, expected_valid, expected_reason in CASES:
        ok, reason = validate_proposal_format(text, file_rel)
        if ok == expected_valid and (expected_reason == "" or expected_reason in reason):
            status = "PASS"
            passed += 1
        else:
            status = "FAIL"
            failed += 1
        print(f"{status}: {desc}")
        if status == "FAIL":
            print(f"  expected valid={expected_valid}, reason substring={expected_reason!r}")
            print(f"  got      valid={ok}, reason={reason!r}")
    print()
    print(f"Summary: {passed} pass, {failed} fail")
    sys.exit(0 if failed == 0 else 1)


if __name__ == '__main__':
    main()
