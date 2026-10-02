"""Publish ``docs/`` to the public site repository and enable Pages.

The application repository is private, and GitHub Pages only serves private
repositories on a paid plan. So the built site is pushed to a separate *public*
repository, ``github-manager-site``, which does serve Pages on the free plan.

The documentation source stays in this repository (``docs_src/`` plus
``tools/build_docs.py``); only the generated output is copied across, so there
is exactly one place to edit a page.

Usage:
    python tools/deploy_site.py              # build and push
    python tools/deploy_site.py --dry-run    # build and show what would change
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
BUILD = ROOT / "tools" / "build_docs.py"

DEFAULT_SITE_REPO = "https://github.com/mrlurix/github-manager-site.git"

#: Files copied into the site repository root.
INCLUDE = ["*.html", "assets", "search-index.json", ".nojekyll"]

#: Explains, in the site repo itself, where the content comes from.
SITE_README = """# GitHub Manager — documentation site

This repository is **generated**. Do not edit it by hand.

The source lives in the private application repository, in `docs_src/`:

    docs_src/pages/*.md          the pages
    docs_src/assets/*            stylesheet, search engine, behaviour
    tools/build_docs.py          renders markdown to HTML + a search index
    tools/deploy_site.py         pushes the result here

To change a page, edit it there and re-run the deploy:

    python tools/build_docs.py
    python tools/deploy_site.py

The search index is a plain JSON file and the search runs entirely in the
browser, so the site has no runtime dependencies and no build service behind it.

Licence: MIT, same as the application.
"""


def run(args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    printable = " ".join(args)
    if check:
        result = subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  failed: {printable}")
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            raise SystemExit(result.returncode)
        return result
    return subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True, text=True)


def build() -> None:
    print("building the site...")
    result = run([sys.executable, str(BUILD)])
    for line in result.stdout.strip().splitlines():
        print("  " + line)


def collect(docs: Path) -> list[Path]:
    """Top-level entries that make up the site, in a stable order."""
    entries: list[Path] = []
    for pattern in INCLUDE:
        for path in sorted(docs.glob(pattern)):
            if path.name == ".nojekyll" and not path.exists():
                continue
            entries.append(path)
    return entries


def publish(site_repo: str, dry_run: bool) -> None:
    if not DOCS.is_dir():
        print("docs/ does not exist - run build_docs.py first", file=sys.stderr)
        raise SystemExit(1)

    entries = collect(DOCS)
    names = ", ".join(p.name for p in entries)
    print(f"site contents: {names}")

    with tempfile.TemporaryDirectory(prefix="ghm-site-") as tmp:
        work = Path(tmp) / "site"
        print(f"cloning {site_repo}...")
        run(["git", "clone", "--depth", "1", site_repo, str(work)])
        run(["git", "config", "user.name", "mrlurix"], cwd=work)
        run(["git", "config", "user.email", "mohamadhasan1388@yahoo.com"], cwd=work)

        # Replace the whole tree so removed pages do not linger.
        for existing in work.iterdir():
            if existing.name == ".git":
                continue
            if existing.is_dir():
                shutil.rmtree(existing)
            else:
                existing.unlink()

        for entry in entries:
            target = work / entry.name
            if entry.is_dir():
                shutil.copytree(entry, target)
            else:
                shutil.copy2(entry, target)
        (work / "README.md").write_text(SITE_README, encoding="utf-8")

        run(["git", "add", "-A"], cwd=work)
        changed = run(["git", "status", "--porcelain"], cwd=work).stdout.strip()
        if not changed:
            print("site is already up to date - nothing to push")
            return

        print("changed files:")
        for line in changed.splitlines()[:12]:
            print("  " + line)
        if len(changed.splitlines()) > 12:
            print(f"  ... and {len(changed.splitlines()) - 12} more")

        if dry_run:
            print("\n--dry-run: stopping before commit")
            return

        run(["git", "commit", "-q", "-m", "Update documentation site"], cwd=work)
        run(["git", "push", "origin", "HEAD"], cwd=work)
        print("pushed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_SITE_REPO, help="site repository URL")
    parser.add_argument("--dry-run", action="store_true", help="build and report, but do not push")
    args = parser.parse_args()

    build()
    publish(args.repo, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())