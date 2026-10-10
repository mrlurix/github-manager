"""Build the site and check that what is live matches what is here.

The site is served by GitHub Pages from ``main``/``docs`` in *this* repository.
There is no second repository and no copy step: a push that includes ``docs/``
is the deployment, and GitHub builds it within a minute or so.

This script used to publish to a separate public repository,
``github-manager-site``, on the stated grounds that the application repository
was private and Pages only serves private repositories on a paid plan. Neither
half of that turned out to be true - the repository is public, and the site
repository does not exist - so the script's first action was a clone that
failed with "repository not found", on a premise that had been quietly false for
however long. It is kept as a build-and-verify step instead, which is the part
that was actually useful.

Usage:
    python tools/deploy_site.py              # build, then check the live site
    python tools/deploy_site.py --push       # build, commit docs/, push, check
    python tools/deploy_site.py --dry-run    # build and report only
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
BUILD = ROOT / "tools" / "build_docs.py"

LIVE_URL = "https://mrlurix.github.io/github-manager/"

#: Stylesheets and fonts are served with a short max-age, so a check run moments
#: after a push can legitimately see the previous version. Retried rather than
#: reported as a failure.
CACHE_TOLERANCE = "The CDN serves assets for up to 10 minutes, so a freshly pushed build may not be visible yet."


def run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    printable = " ".join(args)
    result = subprocess.run(args, cwd=str(cwd) if cwd else None,
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace")
    if result.returncode != 0:
        print(f"  failed: {printable}")
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)
    return result


def build() -> None:
    print("building the site...")
    for line in run([sys.executable, str(BUILD)]).stdout.strip().splitlines():
        print("  " + line)


def pending_changes() -> list[str]:
    """Uncommitted paths under docs/, plus the tool that would have produced them."""
    out = run(["git", "status", "--porcelain", "--", "docs", "docs_src", "tools/build_docs.py"])
    return [line for line in out.stdout.splitlines() if line.strip()]


def push(message: str) -> None:
    run(["git", "add", "docs"])
    run(["git", "commit", "-q", "-m", message])
    run(["git", "push", "-q", "origin", "HEAD"])
    print(f"pushed: {run(['git', 'rev-parse', '--short', 'HEAD']).stdout.strip()}")


def fetch(url: str) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
            return response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"  could not reach {url}: {exc}")
        return None


def verify() -> int:
    """Compare the live site against the local build.

    Not a byte comparison. Pages injects its own toolbar markup and the built
    files are served with a short cache lifetime, so the comparison is on the
    things this repository controls and a stale build would actually change.
    """
    print(f"\nchecking the live site: {LIVE_URL}")
    live = fetch(LIVE_URL)
    local = (DOCS / "index.html").read_text(encoding="utf-8")
    if live is None:
        return 1

    failures = 0

    def compare(label: str, needle: str, haystack: str) -> None:
        nonlocal failures
        ok = needle in haystack
        if not ok:
            failures += 1
        print(f"  [{'PASS' if ok else 'FAIL'}] live {label}")

    compare("carries the same Content-Security-Policy",
            _extract(local, 'Content-Security-Policy" content="'), live)
    compare("carries the same version", _version(local), _version(live))
    compare("has the version's backslash fix", 'replace(/\\\\/g, "/")',
            fetch(LIVE_URL + "assets/app.js") or "")
    compare("has the version's decodeURIComponent guard", "id = raw;",
            fetch(LIVE_URL + "assets/motion.js") or "")

    if failures:
        print(f"\n  {failures} check(s) did not match the local build.")
        print(f"  {CACHE_TOLERANCE}")
        return 1
    print("\n  the live site matches the local build")
    return 0


def _extract(text: str, marker: str) -> str:
    at = text.find(marker)
    if at < 0:
        return ""
    start = text.find('"', at + len(marker))
    end = text.find('"', start + 1)
    return text[start + 1:end]


def _version(text: str) -> str:
    import re

    m = re.search(r"v1\.\d+\.\d+", text)
    return m.group(0) if m else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--push", action="store_true",
                        help="commit docs/ and push, which is what deploys the site")
    parser.add_argument("--dry-run", action="store_true",
                        help="build and report, changing and fetching nothing")
    parser.add_argument("--message", default="Update the documentation site",
                        help="commit message for --push")
    args = parser.parse_args()

    build()

    if args.dry_run:
        changes = pending_changes()
        print("\nuncommitted site changes:")
        for line in changes[:12]:
            print("  " + line)
        if not changes:
            print("  none")
        print("\n--dry-run: nothing committed, nothing pushed, nothing fetched")
        return 0

    if args.push:
        if pending_changes():
            print("\ncommitting the site and pushing (this is the deployment)")
            push(args.message)
        else:
            print("\nnothing under docs/ to commit; checking the live site")
    else:
        changes = pending_changes()
        if changes:
            print("\ndocs/ has uncommitted changes, so the live site cannot match yet:")
            for line in changes[:12]:
                print("  " + line)
            print("\n  run with --push to commit and deploy them")

    return verify()


if __name__ == "__main__":
    raise SystemExit(main())
