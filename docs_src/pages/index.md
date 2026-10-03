---
title: Home
description: GitHub Manager â€” a portable GitHub desktop client with an AI assistant that only ever works on GitHub.
---

<div class="hero">
  <h1>All of GitHub, in one desktop app</h1>
  <p>
    Write READMEs, manage repositories, work through issues and pull requests,
    publish releases and write commit messages â€” with an AI assistant that does
    the work and refuses anything outside GitHub before the request ever reaches
    the model.
  </p>
  <div class="hero-actions">
    <a class="btn btn-primary" href="https://github.com/mrlurix/github-manager/releases/latest">Download 1.2.0</a>
    <a class="btn" href="features.html">Features</a>
    <a class="btn" href="install.html">Getting started</a>
  </div>
</div>

<div class="cards">
  <div class="card">
    <h3>README Studio</h3>
    <p>Builds a complete README from the actual repository contents, refines it when you ask, and commits it when you approve.</p>
  </div>
  <div class="card">
    <h3>Repositories</h3>
    <p>Create, edit, archive, delete, fork, star and change topics â€” all from inside the app, every write confirmed first.</p>
  </div>
  <div class="card">
    <h3>Issues &amp; pull requests</h3>
    <p>Draft an issue, triage a whole queue at once, reply to review comments, and close or reopen anything.</p>
  </div>
  <div class="card">
    <h3>Releases &amp; commits</h3>
    <p>Turns a raw commit list into release notes, writes Conventional Commit messages, suggests branch names and publishes.</p>
  </div>
  <div class="card">
    <h3>Scoped to GitHub</h3>
    <p>Off-topic requests are detected and refused before they are sent to the model.</p>
  </div>
  <div class="card">
    <h3>Portable</h3>
    <p>One exe file. No installer, no Python, no admin rights. A local model works too.</p>
  </div>
</div>

## What this app will not do

It is deliberately limited. The built-in assistant does not answer anything
outside GitHub: not recipes, not medical advice, not stock prices. If a request
falls outside the domain it is blocked before it reaches the model and you get an
out-of-scope reply instead.

<span class="pill pill-ok">Scope is enforced</span>
<span class="pill">Works fully offline with a local model</span>
<span class="pill">Nothing leaves the machine without your say-so</span>

## How it works

1. **Connect** â€” create a Personal Access Token on GitHub and paste it in. The token is encrypted with Windows DPAPI.
2. **Pick a model** â€” any OpenAI compatible endpoint: OpenAI, OpenRouter, Groq, Together, Ollama or LM Studio. A local model needs no API key.
3. **Work** â€” generate a README, triage issues, publish a release. Every write shows a confirmation first.

```text
Connect  â†’  Pick a repository  â†’  Ask the AI  â†’  Review and approve  â†’  Commit to GitHub
```

## Requirements

| | |
| --- | --- |
| OS | 64-bit Windows (tested on 10 and 11) |
| Python | not required â€” the exe is self-contained |
| Disk | roughly 130 MB while running |
| Network | GitHub, plus whichever AI provider you configure |

## Next

- [Features](features.html) â€” every page of the app in detail
- [Getting started](install.html) â€” download and first run
- [AI](ai.html) â€” choosing a model and how the scope limit works
- [Security](security.html) â€” tokens, path validation and HTML sanitising
- [FAQ](faq.html) â€” the questions that come up most