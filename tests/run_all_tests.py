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

    results: list[tuple[str, int]] = []
    for suite in SUITES:
        print(f"\n{'=' * 60}\n  {suite}\n{'=' * 60}")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tests" / suite)],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
        output = proc.stdout + proc.stderr
        lines = [line for line in output.splitlines() if line.strip()]
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
