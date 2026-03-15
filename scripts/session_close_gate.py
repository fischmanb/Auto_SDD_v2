#!/usr/bin/env python3
"""Session Close Gate — deterministic consistency check.

Run this before ending any session. It verifies that the codebase,
tests, and documentation are internally consistent. Exit 0 = clean
close. Exit 1 = prints what's wrong.

Usage:
    cd Auto_SDD_v2
    .venv/bin/python scripts/session_close_gate.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXEC_GATES_DIR = ROOT / "py" / "auto_sdd" / "exec_gates"
TESTS_DIR = ROOT / "py" / "tests"
DOCS_DIR = ROOT / "docs"

failures: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)
    print(f"  FAIL: {msg}")


def ok(msg: str) -> None:
    print(f"  OK:   {msg}")


# ── Check 1: Test ↔ module 1:1 mapping ──────────────────────────────────────

def check_test_module_mapping() -> None:
    print("\n[1] Test ↔ module 1:1 mapping")

    eg_modules = sorted(
        p.stem for p in EXEC_GATES_DIR.glob("eg*.py")
        if not p.stem.startswith("__")
    )
    eg_tests = sorted(
        p.stem for p in TESTS_DIR.glob("test_eg*.py")
    )

    # Build mapping: test short name → module full name
    # test_eg1.py covers eg1_tool_calls.py, test_eg2.py covers eg2_signal_parse.py, etc.
    # Match by prefix: strip "test_" from test stem, find module that starts with it.
    test_to_mod: dict[str, str | None] = {}
    for test_stem in eg_tests:
        prefix = test_stem.replace("test_", "")  # "eg1", "eg2", etc.
        match = next((m for m in eg_modules if m.startswith(prefix)), None)
        test_to_mod[test_stem] = match

    mod_covered = set(test_to_mod.values()) - {None}

    for mod in eg_modules:
        if mod in mod_covered:
            test_name = next(t for t, m in test_to_mod.items() if m == mod)
            ok(f"{mod} covered by {test_name}.py")
        else:
            fail(f"{mod} has no matching test file")

    for test_stem, mod in test_to_mod.items():
        if mod is None:
            fail(f"{test_stem}.py has no matching module")


# ── Check 2: Test imports resolve ────────────────────────────────────────────

def check_test_imports() -> None:
    print("\n[2] Test imports resolve")

    for test_file in sorted(TESTS_DIR.glob("test_eg*.py")):
        text = test_file.read_text()
        for m in re.finditer(r"from auto_sdd\.exec_gates\.(\w+) import", text):
            module_name = m.group(1)
            module_path = EXEC_GATES_DIR / f"{module_name}.py"
            if module_path.exists():
                ok(f"{test_file.name} → {module_name}.py")
            else:
                fail(
                    f"{test_file.name} imports '{module_name}' "
                    f"but {module_path} does not exist"
                )


# ── Check 3: All tests pass ─────────────────────────────────────────────────

def check_tests_pass() -> tuple[bool, int]:
    print("\n[3] All tests pass")

    result = subprocess.run(
        [str(ROOT / ".venv" / "bin" / "python"), "-m", "pytest",
         str(TESTS_DIR), "-q", "--tb=line"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=120,
    )

    # Parse test count from pytest output (e.g., "158 passed")
    count_match = re.search(r"(\d+) passed", result.stdout)
    test_count = int(count_match.group(1)) if count_match else 0

    if result.returncode == 0:
        ok(f"{test_count} tests passed")
        return True, test_count
    else:
        fail(f"pytest exited {result.returncode}")
        # Show first few failure lines
        for line in result.stdout.splitlines()[-10:]:
            if line.strip():
                print(f"        {line}")
        return False, test_count


# ── Check 4: Test count in docs matches actual ──────────────────────────────

def check_doc_test_count(actual_count: int) -> None:
    print("\n[4] Test count in docs matches actual")

    inv_path = DOCS_DIR / "system-inventory.md"
    if not inv_path.exists():
        fail("system-inventory.md not found")
        return

    text = inv_path.read_text()
    m = re.search(r"Tests passing\s*\|\s*\*\*(\d+)\*\*", text)
    if not m:
        fail("Could not parse test count from system-inventory.md")
        return

    doc_count = int(m.group(1))
    if doc_count == actual_count:
        ok(f"system-inventory.md says {doc_count}, actual {actual_count}")
    else:
        fail(
            f"system-inventory.md says {doc_count} tests, "
            f"but actual is {actual_count}"
        )


# ── Check 5: Doc dates are current ──────────────────────────────────────────

def check_doc_dates() -> None:
    print("\n[5] Doc dates are current")

    today = date.today().isoformat()  # e.g., "2026-03-15"
    files_to_check = [
        DOCS_DIR / "SESSION-STATE.md",
        DOCS_DIR / "system-inventory.md",
    ]

    for path in files_to_check:
        if not path.exists():
            fail(f"{path.name} not found")
            continue
        text = path.read_text()
        if today in text:
            ok(f"{path.name} contains today's date ({today})")
        else:
            fail(f"{path.name} does not contain today's date ({today})")


# ── Check 6: No orphan module references in docs ────────────────────────────

def check_orphan_references() -> None:
    print("\n[6] No orphan module references in docs")

    existing_modules = {
        p.stem for p in EXEC_GATES_DIR.glob("eg*.py")
        if not p.stem.startswith("__")
    }

    eg_pattern = re.compile(r"\beg\d+_\w+\.py\b")

    for doc in sorted(DOCS_DIR.glob("*.md")):
        text = doc.read_text()
        for m in eg_pattern.finditer(text):
            ref = m.group(0)
            module_name = ref.replace(".py", "")
            if module_name in existing_modules:
                ok(f"{doc.name} → {ref}")
            else:
                fail(f"{doc.name} references '{ref}' which does not exist")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("SESSION CLOSE GATE")
    print("=" * 60)

    check_test_module_mapping()
    check_test_imports()
    tests_passed, test_count = check_tests_pass()
    if tests_passed:
        check_doc_test_count(test_count)
    else:
        print("\n  [4] Skipped (tests failed)")
    check_doc_dates()
    check_orphan_references()

    print("\n" + "=" * 60)
    if failures:
        print(f"GATE FAILED — {len(failures)} issue(s):")
        for f in failures:
            print(f"  • {f}")
        sys.exit(1)
    else:
        print("GATE PASSED — clean close.")
        sys.exit(0)


if __name__ == "__main__":
    main()
