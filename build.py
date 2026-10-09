"""PyInstaller build script producing a portable single-file Windows exe.

Usage:
    python build.py            # full build
    python build.py --clean    # wipe build artefacts first
    python build.py --onedir   # folder build instead of onefile
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

sys.path.insert(0, str(ROOT))
from app.config import APP_VERSION  # noqa: E402
APP_NAME = "GitHubManager"
ENTRY = ROOT / "main.py"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SPEC = ROOT / f"{APP_NAME}.spec"

HIDDEN_IMPORTS = [
    "PySide6.QtSvg",
    "PySide6.QtNetwork",
    "markdown_it",
    "markdown_it.rules_core.linkify",
    "pygments",
    "pygments.lexers",
    "pygments.formatters",
    "requests",
    "urllib3",
    "certifi",
    "github",
    "github.Auth",
    "cryptography",
    "nacl",
]

EXCLUDES = [
    "tkinter",
    "matplotlib",
    "numpy",
    "pandas",
    "scipy",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtMultimedia",
    "PySide6.Qt3DCore",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth",
    "PySide6.QtPositioning",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
]


def run(args: list[str]) -> None:
    print(f"\n$ {' '.join(args)}\n")
    result = subprocess.run(args, cwd=str(ROOT))
    if result.returncode != 0:
        raise SystemExit(f"Command failed with code {result.returncode}")


def make_icon() -> Path | None:
    """Render an .ico at build time so no binary asset is checked in.

    Always regenerated rather than reused if the file is already there. It used
    to short-circuit on ``target.exists()``, which meant a palette or logo
    change shipped with the old icon until someone noticed and deleted the file
    by hand. Rendering seven sizes takes well under a second, and there is no
    version of "stale icon in the release" that is worth that shortcut.
    """
    target = ROOT / "build_assets" / "icon.ico"
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication

        sys.path.insert(0, str(ROOT))
        from app.ui.widgets import logo_plate_pixmap

        # Held in a name: a QApplication created without a reference can be
        # collected, and rendering a QPixmap with no application alive is a
        # crash rather than a wrong answer.
        app = QApplication.instance() or QApplication([])  # noqa: F841

        # One plate colour has to be chosen for the whole file: an .ico carries
        # no way to say "invert me for a dark taskbar". Dark, because Windows 11
        # defaults to a dark taskbar - and the plate keeps the mark readable on
        # either one, since the mark inside it always has its own background.
        icon = QIcon()
        for size in (16, 24, 32, 48, 64, 128, 256):
            icon.addPixmap(logo_plate_pixmap(dark_plate=True, pixels=size))

        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        # QIcon cannot write .ico, so save the largest pixmap through QImage.
        image = icon.pixmap(QSize(256, 256)).toImage()
        image.save(str(target), "ICO")
        print(f"icon written: {target}")
        return target if target.exists() else None
    except Exception as exc:  # pragma: no cover
        print(f"icon generation skipped: {exc}")
        return None


def version_info(icon: Path | None) -> Path | None:
    """Generate a Windows version resource so the exe has proper metadata.

    The numbers come from APP_VERSION rather than being written out. This used
    to say 1.0.0 while the app was at 1.5.0, which is not merely cosmetic:
    Windows uses the version resource to decide whether a file it has seen
    before has changed, so an exe whose version never moves is an exe a cache is
    entitled to keep serving the old copy of. That is how a replaced executable
    keeps the icon it had three releases ago.
    """
    target = ROOT / "build_assets" / "version_info.txt"
    target.parent.mkdir(parents=True, exist_ok=True)

    # FixedFileInfo wants four integers. A two-part version pads to (1, 5, 0, 0).
    parts = (APP_VERSION.split("-", 1)[0].split(".") + ["0", "0", "0"])[:4]
    quad = ", ".join(str(int(p)) for p in parts)
    target.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({quad}),
    prodvers=({quad}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'GitHub Manager'),
         StringStruct(u'FileDescription', u'GitHub Manager - portable GitHub client'),
         StringStruct(u'FileVersion', u'{APP_VERSION}'),
         StringStruct(u'InternalName', u'{APP_NAME}'),
         StringStruct(u'LegalCopyright', u'MIT'),
         StringStruct(u'OriginalFilename', u'{APP_NAME}.exe'),
         StringStruct(u'ProductName', u'GitHub Manager'),
         StringStruct(u'ProductVersion', u'{APP_VERSION}')])
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
""",
        encoding="utf-8",
    )
    return target


SPEC_TEMPLATE = '''# -*- mode: python ; coding: utf-8 -*-
# Generated by build.py - do not edit by hand.

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports={hiddenimports!r},
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes={excludes!r},
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name={name!r},
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,{icon_line}
)
'''


ONEDIR_TAIL = '''

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name={name!r},
)
'''


def spec_text(icon: Path | None, onedir: bool, version: Path | None = None) -> str:
    """Render the spec for a onefile (default) or onedir PyInstaller build.

    The flag is named ``onedir`` to match ``--onedir`` and its caller; getting
    this backwards silently produces a folder build while the script still
    reports a single portable file.

    ``version`` is passed to PyInstaller as well as generated. It used to be
    written out and then never referenced, so every exe so far reported an empty
    FileVersion in Explorer's properties - and, because Windows uses that field
    to tell one build from another, an exe whose version never moves is one a
    cache is entitled to keep serving an old copy of.
    """
    icon_line = f"\n    icon={str(icon)!r}," if icon else ""
    version_line = f"\n    version={str(version)!r}," if version else ""
    text = SPEC_TEMPLATE.format(
        hiddenimports=HIDDEN_IMPORTS,
        excludes=EXCLUDES,
        name=APP_NAME,
        icon_line=icon_line + version_line,
    )
    if not onedir:
        return text
    return text.replace(
        "exe = EXE(\n    pyz,\n    a.scripts,\n    a.binaries,\n    a.datas,\n    [],",
        "exe = EXE(\n    pyz,\n    a.scripts,\n    [],",
    ) + ONEDIR_TAIL.format(name=APP_NAME)


def main() -> int:
    args = sys.argv[1:]
    clean = "--clean" in args
    onedir = "--onedir" in args

    if "--icon-only" in args:
        # Just the icon. It used to have no way to be rebuilt without running a
        # full PyInstaller pass, which is why the icon in the repo went stale
        # through a whole palette change - nobody was going to do a five-minute
        # build to move a logo.
        icon = make_icon()
        return 0 if icon else 1

    if clean:
        for path in (DIST, BUILD):
            if path.exists():
                print(f"removing {path}")
                shutil.rmtree(path, ignore_errors=True)
        if SPEC.exists():
            SPEC.unlink()

    run([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"])

    icon = make_icon()
    version = version_info(icon)

    SPEC.write_text(spec_text(icon, onedir, version), encoding="utf-8")
    print(f"spec written: {SPEC}")

    run([sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm", "--clean"])

    target = DIST / (f"{APP_NAME}.exe" if not onedir else f"{APP_NAME}/{APP_NAME}.exe")
    if not target.exists():
        print("\nBuild finished but the executable was not found; check dist/.")
        return 1

    size_mb = target.stat().st_size / (1024 * 1024)
    print(f"\nBuild complete: {target}  ({size_mb:.1f} MB)")

    if not onedir:
        # A onefile build must be genuinely self-contained. If a folder build
        # slipped through, the exe silently depends on _internal\ next to it and
        # fails at launch with "Failed to load Python DLL", so catch it here.
        folder = DIST / APP_NAME
        if folder.exists():
            print(
                f"\nERROR: {folder} exists - this is a folder build, not a single "
                "file. The exe would not be portable."
            )
            return 1
        if size_mb < 20:
            print(
                f"\nERROR: the exe is only {size_mb:.1f} MB, which is too small to "
                "contain Qt. It will not start."
            )
            return 1

    print("Copy this single file anywhere - it is fully portable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
