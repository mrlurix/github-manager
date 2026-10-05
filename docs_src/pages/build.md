---
title: Building from source
description: Run the app from source, run the tests, build the exe and build this documentation site.
---

## Running from source

```bash
git clone https://github.com/mrlurix/github-manager.git
cd github-manager
pip install -r requirements.txt
python main.py
```

On Windows you can double-click `run.bat`.

### Requirements

| | |
| --- | --- |
| Python | 3.11 or newer |
| PySide6 | 6.x |
| OS | Windows 10 or 11 (it also runs on Linux and macOS) |

## Building the portable exe

```bash
python build.py --clean
```

Or on Windows, run `build.bat`.

The result is a single file at `dist/GitHubManager.exe`, about 63 MB, with no
dependency on Python. Copy it anywhere.

### Options

| Command | Result |
| --- | --- |
| `python build.py` | normal build |
| `python build.py --clean` | wipe previous artefacts first |
| `python build.py --onedir` | folder build; starts faster |

### What the build script does

- Renders the `.ico` at build time
- Writes the Windows version resource
- Generates the PyInstaller spec itself
- **Checks its own output** — if a folder build slips through instead of a single
  file, or the size is implausible, the build is reported as failed

That last check exists because getting it wrong produces an exe that fails at
launch with `Failed to load Python DLL` and no clue at build time.

Installing [UPX](https://github.com/upx/upx) shrinks it further.

## Running the tests

```bash
python tests/run_all_tests.py
```

Ten suites, around 950 checks. None of them reach the GitHub API or need a token:
the only network traffic is to `tests/mock_github_server.py`, a real HTTP server
running on your own machine.

| Suite | What it covers |
| --- | --- |
| `ai_guard_test.py` | The GitHub-only scope lock |
| `ai_tasks_test.py` | Every AI task function and JSON parsing |
| `security_test.py` | Token redaction, host allow-listing, path validation, HTML sanitising |
| `integration_test.py` | The real client over real HTTP against `mock_github_server.py` |
| `upload_test.py` | File uploads end to end, including binary and the batch dialog |
| `smoke_test.py` | Every page builds and renders |
| `feature_test.py` | Full user flows through the real widgets |
| `ai_flow_test.py` | Streaming, refinement, the commit path and the scope lock |
| `layout_test.py` | Every page at several window sizes |
| `responsive_test.py` | No overlapping or clipped controls from 900×560 to 2560×1440 |

```bash
node tools/verify_site_security.js     # check the generated site and its script
```

`tests/security_test.py` covers the HTML sanitiser, URL allow-listing, path and
ref validation, secret redaction, plaintext transport and the AI prompt fence.
The site check covers the generated pages: each one must carry a
Content-Security-Policy, load no remote asset, keep outbound links on
`noopener`, and contain no inline script or event handler.

### The mock GitHub server

`tests/mock_github_server.py` is a real HTTP server that speaks the GitHub REST
API:

- paginates with a genuine `Link: rel="next"` header
- returns base64 file content
- enforces authentication
- answers with real 401, 403, 404, 422 and 500 bodies

That is why the integration suite can catch things a stub never will — a client
that quietly stops at page one, or that shows a blank error for a rate limit
instead of naming the reset time.

### Keeping the tests out of your data

`tests/_bootstrap.py` redirects the data folder to a temporary directory before
anything is imported. Running the tests therefore **never** touches your real
`data/secrets.json`. That isolation is deliberate: without it a stub token
written by a test would silently overwrite your real one, and because the file is
encrypted you would never find out.

### Development tools

```bash
ruff check app                       # static checks
bandit -r app                        # security scan
node tools/verify_search.js          # test this site's search engine
python tools/screenshot.py shots     # screenshots of every page
python tools/build_docs.py           # build this site (commit docs/ to publish)
```

## Building this site

```bash
python tools/build_docs.py
```

The output is written to `docs/`, which is what GitHub Pages serves. No Node, no
npm and no other build step is involved.

| File | Role |
| --- | --- |
| `docs_src/pages/*.md` | the pages |
| `docs_src/assets/style.css` | layout, light and dark themes |
| `docs_src/assets/search.js` | the search engine |
| `docs_src/assets/app.js` | theme, mobile menu, wiring up the search |
| `docs/` | the generated output, committed to the repository |

The build also verifies that no page links to a page or heading anchor that does
not exist.

### Why the search is hand-written

The content is English, but a generic index still breaks on what technical prose
actually contains: `Ctrl+N` against `ctrl n`, a curly apostrophe against a
straight one, and an accented letter that an ASCII `\w` class would cut out of
the middle of a word. Arabic text appears too, wherever a Persian README is
discussed.

Both sides — the Python index builder and the browser — apply the same
normalisation, and they have to agree step for step or a query silently stops
matching text that is visibly right in front of you. That contract is what
`tools/verify_search.js` checks, alongside the ranking and snippet behaviour.

## Project layout

```text
app/
  config.py              portable paths and settings
  core/                  no Qt imports anywhere in here
    github_api.py        GitHub REST client
    ai_api.py            OpenAI compatible chat client, with streaming
    ai_guard.py          the GitHub-only scope lock
    ai_tasks.py          every AI feature, as a function
    redact.py            scrubbing token-shaped text out of errors
    secure.py            encrypted secret storage
  ui/
    theme.py             palettes, typography, the global QSS
    sanitize.py          allow-list HTML sanitiser
    markdown.py          markdown rendering and code highlighting
    editor.py            split editor with live preview
    widgets.py           cards, badges, toasts, flow layout, icons
    workers.py           background tasks with streaming support
    pages/               the ten pages
tests/
tools/
docs_src/                site source
docs/                    generated site
```

> One thing worth knowing about `app/core/`: it imports nothing from Qt on
> purpose. That is what lets the GitHub and AI logic be tested without starting
> a UI, and what allows the integration suite to drive the real client over real
> HTTP.