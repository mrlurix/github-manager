"""Crop (and optionally zoom) a region of a PNG for visual inspection.

Usage:
    python tools/crop.py input.png x y width height [scale] [output.png]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QPixmap  # noqa: E402


def main() -> int:
    source = Path(sys.argv[1])
    x, y, w, h = (int(v) for v in sys.argv[2:6])
    scale = int(sys.argv[6]) if len(sys.argv) > 6 else 2
    target = Path(sys.argv[7]) if len(sys.argv) > 7 else Path("screenshots/_crop.png")

    QGuiApplication.instance() or QGuiApplication(sys.argv)

    pixmap = QPixmap(str(source))
    if pixmap.isNull():
        print(f"could not load {source}")
        return 1

    crop = pixmap.copy(QRect(x, y, w, h))
    if scale > 1:
        crop = crop.scaled(
            crop.width() * scale,
            crop.height() * scale,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    if not crop.save(str(target)):
        print(f"failed to write {target}")
        return 1
    print(f"saved {target} {crop.width()}x{crop.height()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
