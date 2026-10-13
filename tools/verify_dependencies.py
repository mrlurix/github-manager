"""Check the installed dependencies against a floor.

What this is, stated plainly so it is not oversold: a floor check. It knows the
versions this project has decided it will not run below, and it fails when one
of them is not met. It does **not** query an advisory database, it does not
know whether a version above the floor is clean, and it cannot tell you that.

That is still worth having, because "we depend on requests" is not a decision
anyone made deliberately - it is transitive, and it drifts. A floor that fails
the build turns that drift into something a person chooses to accept or fix.

The floors live here, in one table, so raising one is a visible edit with a
reason attached rather than a number buried in a requirements file.

Run:  python tools/verify_dependencies.py
"""

from __future__ import annotations

import re
import sys
from importlib import metadata

#: package -> (minimum version, why it matters here)
#:
#: Only packages this project actually puts between a credential and the
#: network, plus the ones whose parser bugs would be reachable from untrusted
#: text. PySide6 is checked too because the whole UI is built from markdown
#: rendered out of repository content.
FLOORS: dict[str, tuple[str, str]] = {
    "requests": ("2.32", "carries the GitHub token and the AI API key"),
    "urllib3": ("2.2", "TLS and redirect handling under requests"),
    "certifi": ("2024.7.4", "the root store the TLS chain is verified against"),
    "cryptography": ("42.0", "PyGithub's transport, and the keystore backend"),
    "PySide6": ("6.6", "renders markdown built from repository content"),
    "markdown-it-py": ("3.0", "parses the markdown a repository author wrote"),
    "Pygments": ("2.17", "highlights code inside that markdown"),
    "PyGithub": ("2.1", "optional, but used when present"),
}

#: Packages that are genuinely optional. Absent is a pass, not a fail.
OPTIONAL = {"PyGithub", "linkify-it-py", "keyring"}


def _version_tuple(text: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", str(text or ""))
    return tuple(int(n) for n in numbers[:4]) or (0,)


def main() -> int:
    failures: list[str] = []
    notes: list[str] = []

    print("installed dependencies against the project's floor:\n")
    for package, (floor, why) in sorted(FLOORS.items()):
        try:
            installed = metadata.version(package)
        except metadata.PackageNotFoundError:
            if package in OPTIONAL:
                notes.append(f"  {package:<16} not installed (optional)")
            else:
                failures.append(f"  {package:<16} MISSING - {why}")
            continue

        if _version_tuple(installed) >= _version_tuple(floor):
            print(f"  {package:<16} {installed:<12} >= {floor}   {why}")
        else:
            failures.append(
                f"  {package:<16} {installed:<12} <  {floor}   {why}"
            )

    for line in notes:
        print(line)

    # keyring decides whether a token is written to disk on macOS and Linux,
    # so its absence is worth stating rather than leaving to be discovered.
    try:
        metadata.version("keyring")
    except metadata.PackageNotFoundError:
        print(
            "\n  keyring is not installed. On Windows that changes nothing - "
            "DPAPI covers it.\n  On macOS and Linux the token is kept in memory "
            "for the session only and\n  is never written to disk. Install it to "
            "persist the token between launches."
        )

    if failures:
        print("\nBELOW THE FLOOR - upgrade before trusting this build:\n")
        for line in failures:
            print(line)
        return 1

    print("\nAll floors met.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
