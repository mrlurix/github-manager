---
title: Home
description: GitHub Manager — a portable GitHub desktop client with an AI assistant that only ever works on GitHub.
---

<div class="hero">
  <h1>All of GitHub, in one desktop app</h1>
  <p>
    Write READMEs, manage repositories, work through issues and pull requests,
    publish releases and write commit messages — with an AI assistant that does
    the work and refuses anything outside GitHub before the request ever reaches
    the model.
  </p>
  <div class="hero-actions">
    <a class="btn btn-primary" href="https://github.com/mrlurix/github-manager/releases/latest">Download 1.3.0</a>
    <a class="btn" href="install.html">Getting started</a>
    <a class="btn" href="features.html">Features</a>
  </div>
</div>

<div class="cards">
  <div class="card">
    <h3>README Studio</h3>
    <p>Builds a complete README from the real repository contents, refines it on request, and commits it once you approve.</p>
  </div>
  <div class="card">
    <h3>Repositories</h3>
    <p>Create, edit, archive, delete, fork, star and change topics — including adding and removing files.</p>
  </div>
  <div class="card">
    <h3>Issues &amp; pull requests</h3>
    <p>Draft an issue, triage a whole queue at once, reply to review comments, close or reopen anything.</p>
  </div>
  <div class="card">
    <h3>Releases &amp; commits</h3>
    <p>Turns a raw commit list into release notes, writes Conventional Commit messages, suggests branch names.</p>
  </div>
  <div class="card">
    <h3>Scoped to GitHub</h3>
    <p>Off-topic requests are refused before they are sent to the model, not after the answer comes back.</p>
  </div>
  <div class="card">
    <h3>Portable</h3>
    <p>One exe file. No installer, no Python, no admin rights. Works fully offline with a local model.</p>
  </div>
</div>

## How it works

Four steps, and you can stop after any of them.

1. **Connect.** Create a Personal Access Token on GitHub and paste it in. It is
   encrypted with Windows DPAPI and stored only next to the executable.
2. **Pick a model.** Any OpenAI compatible endpoint — OpenAI, OpenRouter, Groq,
   Together, Ollama or LM Studio. A local model needs no API key at all.
3. **Ask for the work.** Generate a README, triage a queue, draft release notes.
4. **Review and approve.** Every write to GitHub is confirmed first. Nothing is
   committed, published or deleted without you seeing exactly what will happen.

```text
Connect → Pick a repository → Ask the AI → Review and approve → Commit to GitHub
```

## What it will not do

The assistant is deliberately limited to GitHub. It will not answer questions
about recipes, medical advice, law, or share prices. If a request falls outside
that domain it is blocked before it reaches the model, and you get an
out-of-scope reply rather than an answer that happens to be wrong.

<span class="pill pill-ok">Scope is enforced before the request is sent</span>
<span class="pill">Works offline with a local model</span>
<span class="pill">Nothing leaves the machine without your say-so</span>

## Requirements

| | |
| --- | --- |
| OS | 64-bit Windows, tested on 10 and 11 |
| Python | not required — the exe is self-contained |
| Disk | roughly 130 MB while running |
| Network | GitHub, plus whichever AI provider you configure |

## Where to go next

| If you want to | Read |
| --- | --- |
| See every page of the app | [Features](features.html) |
| Download it and connect a token | [Getting started](install.html) |
| Choose a model, or run one locally | [AI](ai.html) |
| Know how your token and files are handled | [Security](security.html) |
| Build the exe or the site yourself | [Building from source](build.html) |
| Look up something specific | [FAQ](faq.html) |