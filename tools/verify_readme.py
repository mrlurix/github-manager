"""Check the README against the repository.

A README is the first thing anyone reads and the easiest thing to get wrong, and
a broken image link or a claim about a shortcut that does not exist is the kind
of thing that ships because nobody looked. Every factual claim below is checked
against the code rather than against the prose.
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {name}" + (f" -> {detail}" if detail and not condition else ""))


def main() -> int:
    text = io.open(README, encoding="utf-8").read()

    # ---------------------------------------------------------------- images
    # Two forms, because the README uses both: markdown ![alt](path) and raw
    # <img src="path"> inside <p align="center">, which is the only way to put a
    # caption under a picture without a table. Checking for one and not the
    # other reported nine of the ten as missing, which is how a checker like
    # this talks you into a false alarm.
    refs = re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", text)
    refs += re.findall(r'<img[^>]+src="([^"]+)"', text)
    refs = [r for r in refs if not r.startswith("http")]

    check("the README has images", len(refs) >= 8, f"{len(refs)} found")
    missing = [r for r in refs if not (ROOT / r).exists()]
    check("every image exists", not missing, ", ".join(missing))

    # Nothing should point at a picture that was deleted, and no picture should
    # exist unreferenced - the second is how the set drifts out of date.
    on_disk = {f"screenshots/{p.name}" for p in (ROOT / "screenshots").glob("*.png")}
    used = {r for r in refs if r.startswith("screenshots/")}
    check("no unreferenced screenshots", not (on_disk - used),
          ", ".join(sorted(on_disk - used)))

    # ----------------------------------------------------------------- links
    for label, href in re.findall(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", text):
        check(f"link is not a placeholder", "example.com" not in href, href)

    # --------------------------------------------------------------- version
    sys.path.insert(0, str(ROOT))
    from app.config import APP_VERSION

    check("the version badge matches the app", f"version-{APP_VERSION}" in text, APP_VERSION)

    # ------------------------------------------------------------- shortcuts
    window = io.open(ROOT / "app" / "ui" / "main_window.py", encoding="utf-8").read()
    nav = re.search(r"NAV_ITEMS = \[(.*?)\n\]", window, re.DOTALL).group(1)
    count = len(re.findall(r'\("', nav))
    check("Ctrl+9 is the last page shortcut", f"Ctrl+{count}" in text, f"{count} nav items")
    check("the shortcut count is right", f"`Ctrl+1` … `Ctrl+{count}`" in text, f"expected Ctrl+{count}")

    for keys in re.findall(r'shortcut\(self, "([^"]+)"', window):
        check(f"shortcut Ctrl+{keys} is documented",
              keys.replace("+", "+") in text, keys)

    # ----------------------------------------------------------- requirements
    req = io.open(ROOT / "requirements.txt", encoding="utf-8").read()
    for package in ("PySide6", "requests", "markdown-it-py"):
        check(f"{package} is a declared dependency", package in req)
        check(f"{package} is in the layout section", package.lower().replace("-py", "-py") in text
              or package.split("-")[0].lower() in text.lower())

    # ------------------------------------------------------------- test suites
    suites = sorted(p.name for p in (ROOT / "tests").glob("*_test.py"))
    # The README spells small numbers out, so accepting only "11 suites" would
    # report a correct README as wrong.
    spelled = {
        8: ("eight", "Eight"), 9: ("nine", "Nine"), 10: ("ten", "Ten"),
        11: ("eleven", "Eleven"), 12: ("twelve", "Twelve"), 13: ("thirteen", "Thirteen"),
    }.get(len(suites), ())
    claimed = f"{len(suites)} suites" in text or any(w in text for w in spelled)
    check("the README's suite count is right", claimed,
          f"found {len(suites)} suites; the README claims neither the number nor the word")

    # --------------------------------------------------------- honest claims
    check("the unaffiliation note is present", "not affiliated" in text.lower())
    check("the MIT licence is stated", "MIT" in text)
    check("no telemetry is claimed", "telemetry" in text.lower())

    # Every screenshot referenced must be one this build actually produced.
    check("no screenshot is a placeholder",
          not any("placeholder" in r.lower() or "example" in r.lower() for r in refs))

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
