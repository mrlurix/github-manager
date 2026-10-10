"""Runs every test suite in this folder and reports a single summary.

Usage:
    python tests/run_all_tests.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITES = [
    "ai_guard_test.py",
    "ai_tasks_test.py",
    "security_test.py",
    "docs_build_test.py",
    "integration_test.py",
    "upload_test.py",
    "smoke_test.py",
    "feature_test.py",
    "ai_flow_test.py",
    "layout_test.py",
    "responsive_test.py",
    "repo_admin_test.py",
]


def main() -> int:
    env = dict(os.environ)
    # Headless: the UI tests must not try to open a real window.
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    # The suites print filenames with accents in them. On Windows a pipe gets
    # the console's code page, so a suite that printed "café.md" as cp1252 left
    # a 0xe9 that the parent's reader thread could not decode as UTF-8 - which
    # raised inside the reader and silently truncated that suite's captured
    # output. A runner that can lose a suite's output can lose a failure, so
    # both ends are pinned to UTF-8 rather than left to the locale.
    env["PYTHONIOENCODING"] = "utf-8"

    results: list[tuple[str, int]] = []
    for suite in SUITES:
        print(f"\n{'=' * 60}\n  {suite}\n{'=' * 60}")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tests" / suite)],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        lines = [line for line in output.splitlines() if line.strip()]
        if not lines:
            # A suite with no output did not report a failed assertion, it
            # died. Saying so is the difference between a runner that names
            # what happened and one that crashes on the None it got back,
            # naming neither the suite nor the cause.
            print(f"  no output; exited with code {proc.returncode}")
        for line in lines[-4:]:
            print(line)
        results.append((suite, proc.returncode))

    print(f"\n{'=' * 60}\n  SUMMARY\n{'=' * 60}")
    failed = 0
    for suite, code in results:
        failed += 0 if code == 0 else 1
        print(f"  [{'PASS' if code == 0 else 'FAIL'}] {suite}")

    print(f"\n{len(results) - failed}/{len(results)} suites passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
