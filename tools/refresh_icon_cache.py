"""Clear the Windows icon and thumbnail cache, then restart Explorer.

Replacing an executable does not reliably replace the icon Windows shows for
it. Explorer keeps a decoded bitmap keyed on the path, and the key is checked
against size and timestamps rather than content - so an exe swapped for one of
the same size can keep the icon it had for months. That is the whole of the
"the logo is still the old one" report: nothing is wrong with the file.

This clears the caches and restarts Explorer, which is the only thing that
actually forces a redraw. It closes open File Explorer windows, which come back
by themselves a second or two later.

Run:
    python tools/refresh_icon_cache.py            # ask first
    python tools/refresh_icon_cache.py --yes      # do not ask
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from pathlib import Path

#: Where Explorer keeps its caches. Both are plain files and are rebuilt from
#: scratch; deleting them is safe and is Microsoft's own documented remedy.
CACHES = [
    Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Explorer",
    Path.home() / "AppData" / "Local" / "IconCache.db",
]

#: Only these are ours. The folder holds a great deal that is not an icon.
PATTERNS = ("iconcache*", "thumbcache*")

ctypes.windll.shell32.SHChangeNotify(
    0x08000000,  # SHCNE_ASSOCCHANGED
    0x1000,      # SHCNF_IDLIST
    None,
    None,
)


def explorer_running() -> bool:
    return bool(ctypes.windll.shell32.IsWindow(
        ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None)
    ))


def stop_explorer() -> None:
    subprocess.run(
        ["taskkill", "/f", "/im", "explorer.exe"],
        capture_output=True,
        check=False,
    )
    time.sleep(1.2)


def start_explorer() -> None:
    subprocess.Popen(
        ["explorer.exe"],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    time.sleep(1.5)


def main() -> int:
    forced = "--yes" in sys.argv

    print("This closes your File Explorer windows and brings them back.")
    if not forced:
        answer = input("Continue? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Cancelled. Nothing was changed.")
            return 0

    stop_explorer()

    removed = 0
    for path in CACHES:
        try:
            if path.is_dir():
                for pattern in PATTERNS:
                    for hit in path.glob(pattern):
                        hit.unlink(missing_ok=True)
                        removed += 1
            elif path.exists():
                path.unlink(missing_ok=True)
                removed += 1
        except OSError as exc:
            # A cache file held open by another process is normal and not worth
            # failing over - the restart below is what actually matters.
            print(f"  could not remove {path.name}: {exc.strerror}")

    print(f"removed {removed} cache file(s)")

    start_explorer()
    print("Explorer restarted. If an icon is still stale, press F5 on the desktop.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
