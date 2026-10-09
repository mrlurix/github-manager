"""Build the app mark: the GitHub Octocat with a gear.

One script writes both copies of the logo - the site's and the desktop app's -
because two copies of a logo is one more than there should be. They are the
same geometry, so they can never drift into being two logos that look similar.

The mark itself is the official Octocat path, taken verbatim rather than
redrawn: the silhouette is recognisable only at its exact proportions, and an
approximation of an approximation reads as a bad cat.

The gear is generated rather than hand-drawn so the teeth are even, and its
numbers below were measured off the reference artwork rather than guessed -
the gear is nearly half the width of the circle, its hole is half its radius,
and it overhangs the ring at 45 degrees. A gear tucked inside the circle would
be a shape on a shape; overhanging is the whole point of it being there.

Run:  python tools/make_logo.py
"""
from __future__ import annotations

import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The GitHub mark, read from a copy of the official file rather than pasted in.
#:
#: It was pasted in first, and that is how a coordinate went missing: a
#: 700-character path retyped by hand and split across string literals loses a
#: number silently. The result still parses as valid SVG, so nothing downstream
#: complains - the only symptom is that Qt draws no logo at all, with no error.
#: Reading the file makes the mistake impossible.
#:
#: simple-icons, MIT licensed. Kept byte-for-byte as published so it can be
#: diffed against upstream; do not reformat it.
SOURCE = ROOT / "tools" / "assets" / "github-mark-source.svg"

#: Argument count per path command, used to check the path is well formed.
_ARITY = {"m": 2, "z": 0, "l": 2, "h": 1, "v": 1, "c": 6, "s": 4, "q": 4, "t": 2, "a": 7}
_NUMBER = re.compile(r"-?(?:\d+\.?\d*|\.\d+)")


def load_mark() -> str:
    """The mark's path data, read from the upstream file and sanity-checked.

    The check is the reason for reading the file at all. A path whose last curve
    carries five numbers instead of six is still valid input to every renderer:
    they stop at the end of the data and draw something slightly wrong - or, in
    Qt's case, nothing at all - without complaint. Here it is a build-time error
    that names the command and the offset.
    """
    text = SOURCE.read_text(encoding="utf-8")
    match = re.search(r'<path[^>]*\sd="([^"]+)"', text)
    if match is None:
        raise SystemExit(f"no path with a d attribute in {SOURCE}")
    d = match.group(1)

    command: str | None = None
    index = 0
    while index < len(d):
        if d[index].isalpha():
            command = d[index].lower()
            index += 1
            if command not in _ARITY:
                raise SystemExit(f"unknown path command {command!r} in {SOURCE}")
        if command is None:
            raise SystemExit(f"the path in {SOURCE} starts with a number")
        arity = _ARITY[command]
        if arity == 0:
            continue
        # One command may be followed by any number of implicit repeats of
        # itself, so the run has to divide exactly into groups of its arity.
        while True:
            got = 0
            for _ in range(arity):
                found = _NUMBER.match(d, index)
                if found is None:
                    break
                got += 1
                index = found.end()
                while index < len(d) and d[index] in ", \t":
                    index += 1
            if got == 0:
                break
            if got != arity:
                raise SystemExit(
                    f"command {command!r} at offset {index} in {SOURCE} ends with "
                    f"{got} of {arity} numbers"
                )
    if index != len(d):
        raise SystemExit(
            f"{index} of {len(d)} characters of the path in {SOURCE} were consumed; "
            "it does not parse cleanly"
        )
    return d


MARK = load_mark()

VIEW_BOX = "0 0 24 24"

#: The gear, measured off the reference. Held as one object so the site copy and
#: the app copy are generated from the same numbers in the same call - the
#: alternative is two sets of constants that agree until someone edits one.
GEAR = {
    "cx": 18.3,
    "cy": 18.3,
    "teeth": 8,
    "outer": 5.2,
    "inner": 3.5,
    "bore": 2.6,
}

#: Width of the channel that separates the gear from the cat. In the fill's own
#: colour, because there is nothing behind the mark to knock out to - a browser
#: tab, a taskbar button and the app's own page all have different backgrounds
#: and the logo cannot ask any of them. The app reads this too; see
#: widgets.LOGO_GEAR_GAP.
GEAR_GAP = 0.7


def gear_path(
    cx: float,
    cy: float,
    *,
    teeth: int,
    outer: float,
    inner: float,
    bore: float,
    rotation: float = 0.0,
) -> str:
    """A spur gear as a single closed path, drawn as polar teeth.

    Each tooth is four points: in at the root, out along one flank, across the
    tip, back down the other, in to the root. Sampling the outline at a fixed
    angular interval instead - the obvious approach - gives teeth whose width
    varies with how the gear is rotated, and one that looks wrong the moment it
    is not aligned to a cardinal.

    The bore is a separate subpath rather than part of the outline, because it
    is a hole and not a notch in the rim. The caller fills with ``evenodd``.
    """
    step = 360.0 / teeth
    flank = step * 0.22
    tip = step * 0.28
    root = step * 0.28
    points: list[tuple[float, float]] = []

    for i in range(teeth):
        base = rotation + i * step
        for angle, radius in (
            (base - step / 2 + root / 2, inner),
            (base - flank, outer),
            (base + flank, outer),
            (base + tip, inner),
        ):
            radians = math.radians(angle)
            points.append((cx + radius * math.cos(radians), cy + radius * math.sin(radians)))

    outline = "M" + "L".join(f"{x:.3f} {y:.3f}" for x, y in points) + "Z"

    hole = (
        f"M{cx - bore:.3f} {cy:.3f}"
        f"A{bore:.3f} {bore:.3f} 0 1 0 {cx + bore:.3f} {cy:.3f}"
        f"A{bore:.3f} {bore:.3f} 0 1 0 {cx - bore:.3f} {cy:.3f}Z"
    )
    return outline + hole


def gear_svg(*, fill: str | None = None, gap: str | None = None) -> str:
    """The gear as an SVG path element, ready to drop inside a ``<svg>``.

    ``fill`` is omitted rather than defaulted, because the app's copy is pasted
    into a document that already sets ``fill`` on its root and repeating it on
    the child is how the two copies start disagreeing.
    """
    d = gear_path(GEAR["cx"], GEAR["cy"], **{k: v for k, v in GEAR.items() if k not in ("cx", "cy")})
    attrs = ""
    if fill:
        attrs += f' fill="{fill}"'
    if gap:
        attrs += f' stroke="{gap}" stroke-width="{GEAR_GAP:g}" stroke-linejoin="round"'
    return f'<path d="{d}"{attrs} fill-rule="evenodd"/>'


def logo(
    *,
    colour: str = "currentColor",
    gap: str | None = None,
    title: str | None = None,
) -> str:
    """The full lockup as an SVG string.

    ``gap`` is the colour of the channel around the gear. Left as ``None`` the
    gear simply overlaps the cat, which is what a monochrome mark with no
    separation looks like: one lumpy silhouette.
    """
    head = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{VIEW_BOX}" role="img">']
    if title:
        head.append(f"  <title>{title}</title>")
    body = [
        f'  <path d="{MARK}"/>',
        f"  {gear_svg(fill=colour, gap=gap)}",
    ]
    return "\n".join(head + body) + "\n</svg>\n"


def _py_string(text: str, width: int = 96) -> str:
    """A long string as an implicitly-concatenated Python literal.

    One 700-character line in the middle of a module is unreadable and shows up
    as a wall in every diff that touches it. Split at a fixed width rather than
    at a path boundary: the path has no boundaries, and trying to find a split
    point that is also in the middle of a number is how you get a subtly wrong
    logo.

    Each chunk becomes its own string literal, so the result reads as one value
    and the file stays inside a sane line length.
    """
    chunks = [text[i:i + width] for i in range(0, len(text), width)]
    return "\n".join(f"    '{chunk}'" for chunk in chunks)


#: The Octocat as the literal that goes into widgets.py.
MARK_SPLIT = _py_string(f'<path d="{MARK}"/>')


def write_site_assets() -> list[Path]:
    """The three files the site needs, written into docs_src/assets."""
    out = ROOT / "docs_src" / "assets"
    out.mkdir(parents=True, exist_ok=True)

    written = [
        # Inline in the header and the footer, so currentColor covers both
        # themes and there is no second request.
        out / "logo.svg",
        # The favicon has no cascade to inherit from, so it says what it is -
        # and carries its own separating gap for the same reason.
        out / "favicon.svg",
        # For anything that needs the mark on a dark background with no
        # cascade: the browser's install prompt, a README on a dark profile.
        out / "logo-light.svg",
    ]

    written[0].write_text(logo(title="GitHub Manager"), encoding="utf-8")
    written[1].write_text(
        logo(colour="#0a0a0a", gap="#0a0a0a", title="GitHub Manager"), encoding="utf-8")
    written[2].write_text(
        logo(colour="#ffffff", gap="#ffffff", title="GitHub Manager"), encoding="utf-8")
    return written


def write_app_copy() -> Path | None:
    """Write the gear into app/ui/widgets.py, which is where the app reads it.

    Held as a string in the module rather than as a file the app has to load at
    runtime: it is the first thing drawn, and a portable exe that cannot find an
    asset shows a blank window rather than a window without a logo.

    Returns the path it wrote, or None if the anchor was not found - loudly,
    because a silent failure here is how the two copies start disagreeing.
    """
    widgets = ROOT / "app" / "ui" / "widgets.py"
    text = widgets.read_text(encoding="utf-8")

    # The whole tuple body is rewritten, not one line matched by its content.
    # Matching on the emitted path is what the previous version did, and it has
    # the obvious failure mode: change the attribute order in this script and
    # the anchor stops matching, the write silently does nothing, and the two
    # copies of the logo are now different - which is the entire thing this
    # script exists to prevent. The tuple is unambiguous and always in one file.
    start = text.find("LOGO_PARTS = (")
    if start == -1:
        raise SystemExit(f"no LOGO_PARTS tuple in {widgets}")
    end = text.find("\n)\n", start)
    if end == -1:
        raise SystemExit(f"LOGO_PARTS in {widgets} is not closed on its own line")

    body = (
        "LOGO_PARTS = (\n"
        "    # The Octocat, verbatim from the official mark.\n"
        f"{MARK_SPLIT},\n"
        "    # GENERATED by tools/make_logo.py - do not hand-edit. Re-running that\n"
        "    # script overwrites this line, which is the point: it is generated from\n"
        "    # the same numbers as the site's copy so the two cannot drift.\n"
        f"    '{gear_svg()}',"
    )
    text = text[:start] + body + text[end:]

    # The gap width is part of the same geometry, so it is written in the same
    # pass. Leaving it to a hand edit is how a regenerated gear ends up with a
    # gap sized for a different gear.
    text, subs = re.subn(
        r"^LOGO_GEAR_GAP = .*$",
        f"LOGO_GEAR_GAP = {GEAR_GAP:g}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if subs != 1:
        raise SystemExit(
            f"no LOGO_GEAR_GAP assignment in {widgets}; add one or the app and the "
            "site will size the gear's separating channel differently"
        )

    widgets.write_text(text, encoding="utf-8", newline="\n")
    return widgets


def main() -> None:
    for path in write_site_assets():
        print(f"wrote {path.relative_to(ROOT)}")
    written = write_app_copy()
    print(f"wrote {written.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
