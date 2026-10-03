---
title: Security
description: Token storage, path validation, HTML sanitising, rate limit handling and how far the token can travel.
---

Security in this app is built around one fact: a lot of the text it displays is
text you do **not** control — output from a model, a README from someone else's
repository, the body of an issue written by a stranger. This page explains what
happens to that text.

## The GitHub token

### Storage

- Encrypted with **Windows DPAPI** (`CryptProtectData`)
- Bound to your Windows account — another user on the same machine cannot decrypt it
- Uses an extra entropy value, so only this application can read it back
- On non-Windows systems it is stored obfuscated, written `0600` on POSIX

### Display

- Never shown in the clear anywhere in the UI
- The last character is masked before you submit it
- Every error message, toast and dialog is **scrubbed before it is shown**

### Removing it

- **Settings → Clear API key** removes the model key
- **Settings → Erase everything** removes tokens, keys, the repository cache and settings
- To wipe it by hand, delete the `data` folder next to the executable

## The token never leaves GitHub

The `Authorization` header goes only to the address the app itself configured.
Any other absolute URL is refused:

| URL | Result |
| --- | --- |
| `https://api.github.com/...` | allowed |
| `https://uploads.github.com/...` | allowed (release asset uploads) |
| `https://evil.example.com/...` | refused |
| `https://api.github.com.evil.com/...` | refused |
| `https://user:pass@api.github.com@evil.com/...` | refused |

The check is made on the parsed **hostname**, not on the text of the URL, so
tricks that merely look like the right host do not work.

## Input validation

A repository name can be typed by hand in the picker, so it is not trusted.

| Input | Rule |
| --- | --- |
| Repository name | exactly `owner/repo`, using GitHub's own allowed characters |
| File path | no `..`, no path separator inside a segment |
| Branch name | no space and none of `~ ^ : ? * [ \`, and no trailing `/` |

Anything like `owner/../../user` is refused **before the URL is built**, rather
than being sent and coming back as a 404.

## HTML sanitising

The preview renders into a `QTextBrowser`, which is a real HTML engine: it
fetches images and follows links. Rendered markdown therefore passes through an
**allow-list** sanitiser.

| Threat | What happens |
| --- | --- |
| `<script>`, `<iframe>`, `<object>` | tag and its content removed |
| `onclick` and friends | any attribute starting with `on` removed |
| Image with a `file://` source | limited to `http` and `https` |
| Image with `data:` or a schemeless path | refused |
| `javascript:` or `file:` links | limited to `http`, `https` and `mailto` |
| CSS with `url()` or `@import` | the whole declaration is dropped |
| CSS hiding a keyword with a comment (`ur/**/l(`) | any declaration containing a comment is dropped |
| `<a target="…">` pointing at a named frame | only `_blank` and `_self` are allowed |

On top of that, **every link click is checked again** before the browser opens.
If a future markdown renderer ever slipped past the sanitiser, this layer would
still stop a dangerous URL from launching.

> Remote `http(s)` images **are** loaded so that badges work. That is a conscious
> choice — GitHub does the same thing behind its camo proxy. What remains is that
> a third party can see which repository page was opened.

## Rate limits and error handling

GitHub enforces an hourly quota per token. When it runs out, the API returns 403.

The app **does not retry that**. Retrying after a couple of seconds cannot help,
because the quota returns after minutes, not seconds — all it achieves is freezing
the UI for several seconds before explaining why. Instead:

- The error appears immediately
- The approximate reset time, read from the `X-RateLimit-Reset` header, is included in the message

401 and 422 behave the same way: one request, one clear message, no retry. Only
5xx is retried, because those are genuinely transient.

Every error message passes through the redaction filter, so a service that echoes
your API key back in an error body never shows it on screen.

## What is sent to the model

The exact list is on the [AI](ai.html) page. In short: repository content, and
only when you ask for it.

**Never sent:** your GitHub token, your API key, local file paths, or the
contents of the `data` folder.

## Path handling

When the app opens a file or folder on your behalf, the path is passed to the
system as an argument rather than as a string to a shell. A path containing shell
metacharacters can therefore never be interpreted as a command.

## Write operations

Nothing is written to GitHub without confirmation:

- **Delete repository** — you must type the full repository name
- **Publish release** — a dialog naming the tag and repository
- **Commit a file** — a dialog showing the path, the branch and the message
- **Close an issue or create one** — a confirmation dialog

The AI assistant never writes anything without one of these.

## Reducing your exposure

Give the token the least it can do:

- Only the repositories you really work in
- Skip the delete scope if you do not delete repositories
- `Contents: Read-only` is enough if you only ever read

## Reporting a problem

If you find a security issue, report it privately on the repository so it can be
fixed before it becomes public.