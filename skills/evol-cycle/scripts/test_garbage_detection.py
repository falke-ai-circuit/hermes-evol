#!/usr/bin/env python3
"""Self-test for the multi-line garbage row detector.

Run after any change to _lib.find_garbage_rows_in_text or _lib.GARBAGE_PATTERNS.
Prints PASS/FAIL per case and a summary. Exit 0 = all pass, 1 = at least one fail.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'phases'))
from _lib import find_garbage_rows_in_text  # noqa: E402


CASES = [
    # (description, input_text, expected_garbage_rows)
    # ===== Clean files =====
    ("Empty file",
     "", []),
    ("File with no pipes",
     "Just a plain text file\nwith multiple lines\nand no tables at all.", []),
    ("Three valid Evolution Log rows",
     "| 2026-06-01 | something-rule (wt:0.50) | Some real instruction here |\n"
     "| 2026-06-02 | other-rule (wt:0.60) | Another real instruction |\n"
     "| 2026-06-03 | third-rule (wt:0.70) | A third real instruction |\n",
     []),
    # ===== Bad rows (multi-line) =====
    ("One multi-line bad row",
     "| 2026-06-04 | pending-question-unanswered-rule (wt:0.90) | When pending_questions.md, then ## 2026-06-04T08:42:09 (from EVOL)\n"
     "You are being asked by EVOL during a 6-phase evolution cycle on your profile. Pending questions for you (0): []. Open gaps from reflect (0): []. What do YOU want cha |\n",
     [(1, 2)]),
    ("Valid row + bad row",
     "| 2026-06-03 | good-rule (wt:0.80) | A valid instruction |\n"
     "| 2026-06-04 | bad-rule (wt:0.85) | When X, then some long evidence text\n"
     "spans two lines with the closing pipe on line 2 |\n",
     [(2, 3)]),
    ("Two consecutive bad rows",
     "| 2026-06-04 | first-bad (wt:0.85) | When A, then long text\n"
     "continues on line 2 |\n"
     "| 2026-06-04 | second-bad (wt:0.85) | When B, then long text\n"
     "continues on line 2 |\n",
     [(1, 2), (3, 4)]),
    ("Bad row with pipe in middle of evidence",
     "| 2026-06-04 | weird-rule (wt:0.85) | When |something|, then |a|b|c|\n"
     "but the actual end is on line 2 |\n",
     [(1, 2)]),
    # ===== Boundary =====
    ("Bad row at end of file with no trailing newline",
     "| 2026-06-04 | end-bad (wt:0.85) | When X, then Y\n"
     "spans 2 lines with closing pipe |",
     [(1, 2)]),
]


def main():
    passed = 0
    failed = 0
    for desc, text, expected in CASES:
        got = find_garbage_rows_in_text(text)
        if got == expected:
            status = "PASS"
            passed += 1
        else:
            status = "FAIL"
            failed += 1
        print(f"{status}: {desc}")
        if status == "FAIL":
            print(f"  expected: {expected}")
            print(f"  got:      {got}")
    print()
    print(f"Summary: {passed} pass, {failed} fail")
    sys.exit(0 if failed == 0 else 1)


if __name__ == '__main__':
    main()
