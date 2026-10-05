---
title: Home
description: GitHub Manager — a portable GitHub desktop client with an AI assistant that only ever works on GitHub.
---

<div class="hero">
  <h1>Your GitHub, as a desktop app</h1>
  <p>
    One portable exe that does the work GitHub's website makes you do by hand —
    with an AI assistant that refuses anything outside GitHub before the request
    is ever sent.
  </p>
  <div class="hero-actions">
    <a class="btn btn-primary" href="https://github.com/mrlurix/github-manager/releases/latest">Download 1.4.0</a>
    <a class="btn" href="install.html">Getting started</a>
    <a class="btn" href="features.html">See all features</a>
  </div>
</div>

<div class="cards">
  <div class="card">
    <h3>README Studio</h3>
    <p>A complete README generated from the real repository, refined on request, committed once you approve.</p>
  </div>
  <div class="card">
    <h3>Repositories</h3>
    <p>Create, edit, archive, fork, star, and add or remove files without leaving the app.</p>
  </div>
  <div class="card">
    <h3>Inside a repository</h3>
    <p>Browse files, create branches, read tags, manage collaborators and inspect webhooks.</p>
  </div>
  <div class="card">
    <h3>Issues &amp; PRs</h3>
    <p>Draft issues, triage an entire queue, reply to review comments, close and reopen.</p>
  </div>
  <div class="card">
    <h3>Releases</h3>
    <p>Raw commits turned into release notes, with Conventional Commit messages and branch names.</p>
  </div>
  <div class="card">
    <h3>Scoping</h3>
    <p>Off-topic requests are blocked before they reach the model, not after the answer arrives.</p>
  </div>
  <div class="card">
    <h3>Privacy</h3>
    <p>Token encrypted with Windows DPAPI. Works fully offline with a local model.</p>
  </div>
</div>

## The idea

GitHub's website is good at showing you things and bad at doing them. Every
change means navigating somewhere, finding the right form, and confirming an
action you already decided on. This app inverts that: you say what you want, and
it asks you to confirm the one thing that matters.

## How it works

1. **Connect.** Create a [personal access token](https://github.com/settings/tokens)
   and paste it in. It is encrypted with Windows DPAPI and stored only beside
   the executable.
2. **Choose a model.** Any OpenAI compatible endpoint — OpenAI, OpenRouter,
   Groq, Together, Ollama, or LM Studio. A local model needs no API key at all.
3. **Ask for the work.** Generate a README, triage issues, draft release notes.
4. **Approve and commit.** Every write to GitHub is confirmed first.

```text
Connect → Choose a repository → Ask the AI → Review and approve → Commit
```

## What it will not do

The assistant is deliberately scoped to GitHub. It will not answer questions
about recipes, medical advice, law, or share prices. A request outside that
domain is refused before it reaches the model, so you get a clear answer rather
than a plausible wrong one.

<span class="pill pill-ok">Scope enforced before the request is sent</span>
<span class="pill">Runs offline with a local model</span>
<span class="pill">No telemetry, no analytics</span>

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
| Build the exe or this site yourself | [Building from source](build.html) |
| Look up something specific | [FAQ](faq.html) |