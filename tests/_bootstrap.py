"""Test bootstrap: keep the suites out of the real data folder.

Import this **before** anything from ``app`` is imported.

Without it the tests would resolve the same ``data/secrets.json`` the installed
application uses, so a stub token written by a test would overwrite the user's
real one - and the overwrite is invisible, because the file is encrypted. Every
suite therefore redirects the data folder into a throwaway directory.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

#: Sandbox shared by every suite in one process.
SANDBOX = Path(tempfile.gettempdir()) / "ghm-test-sandbox"

# Start from a clean slate so a stub token left by a previous run can never
# leak into the next one and make an assertion pass for the wrong reason.
if SANDBOX.exists() and SANDBOX.name.startswith("ghm-test-"):
    shutil.rmtree(SANDBOX, ignore_errors=True)

# Force the non-portable branch so nothing is written next to the source tree,
# then point that branch at a throwaway directory.
os.environ["GHM_PORTABLE"] = "0"
os.environ["APPDATA"] = str(SANDBOX)
# Windows also resolves LOCALAPPDATA for some APIs; keep them consistent.
os.environ["LOCALAPPDATA"] = str(SANDBOX)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SANDBOX.mkdir(parents=True, exist_ok=True)


def ensure_importable() -> None:
    """Put the project root and the tests folder on ``sys.path``."""
    root = Path(__file__).resolve().parents[1]
    for entry in (root, root / "tests"):
        text = str(entry)
        if text not in sys.path:
            sys.path.insert(0, text)


ensure_importable()