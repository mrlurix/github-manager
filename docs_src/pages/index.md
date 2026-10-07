---
title: GitHub Manager
description: A portable GitHub client for Windows, with an AI assistant that only ever works on GitHub.
---

<div class="marketing">

<div class="hero">
  <p class="eyebrow" data-reveal="scale"><b>v1.4.0</b> · Windows · one portable file</p>
  <h1 data-reveal="scale">GitHub, as a desktop app</h1>
  <p class="lede" data-reveal="scale">
    A single exe that does the work the website makes you do by hand — with an
    assistant that refuses anything outside GitHub before the request is sent.
  </p>
  <div class="cta-row" data-reveal="scale" data-stagger="1">
    <a class="btn btn-primary" href="https://github.com/mrlurix/github-manager/releases/latest">
      Download for Windows <span class="btn-arrow" aria-hidden="true"></span>
    </a>
    <a class="btn btn-solid" href="install.html">
      Getting started <span class="btn-arrow" aria-hidden="true"></span>
    </a>
  </div>
  <p class="hero-note" data-reveal="fade">63 MB · no installer · no Python</p>
</div>

<div class="shot" data-reveal="scale">
  <div class="shot-bar">
    <span class="shot-dot"></span><span class="shot-dot"></span><span class="shot-dot"></span>
    <span class="shot-title">GitHub Manager — mrlurix / github-manager</span>
  </div>
  <div class="shot-body">
    <div class="shot-nav">
      <i>Dashboard</i>
      <i>README Studio</i>
      <i>Repositories</i>
      <i class="on">Repository</i>
      <i>Issues &amp; PRs</i>
      <i>Releases</i>
      <i>AI Assistant</i>
      <i>Account</i>
      <i>Settings</i>
    </div>
    <div class="shot-main">
      <div class="shot-row">
        <span class="shot-h">Repository</span>
        <span class="shot-p">mrlurix/github-manager</span>
      </div>
      <div class="shot-chips">
        <span class="shot-chip on">Files</span>
        <span class="shot-chip">Branches</span>
        <span class="shot-chip">Tags</span>
        <span class="shot-chip">Collaborators</span>
        <span class="shot-chip">Webhooks</span>
      </div>
      <div class="shot-split">
        <div class="shot-pane">
          <b>docs_src</b><br>
          pages<br>
          assets<br>
          <b>tools</b><br>
          build_docs.py<br>
          verify_search.js
        </div>
        <div class="shot-pane">
          <b>app</b><br>
          core/github_api.py<br>
          ui/pages/repo_admin.py<br>
          <em>10 pages, one executable</em>
        </div>
      </div>
    </div>
  </div>
</div>

<section class="section">
  <div class="bento">
    <div data-reveal data-stagger="1">
      <h3>README Studio</h3>
      <p>A README written from the real repository — its tree, its languages, its topics — refined on request and committed once you approve.</p>
    </div>
    <div data-reveal data-stagger="1">
      <h3>Repositories</h3>
      <p>Create, edit, archive, fork and star, with files attached at creation and removable afterwards.</p>
    </div>
    <div data-reveal data-stagger="1">
      <h3>Inside one</h3>
      <p>Browse the file tree, create branches, read tags, set collaborator permissions, inspect webhooks.</p>
    </div>
    <div data-reveal data-stagger="1">
      <h3>Issues &amp; PRs</h3>
      <p>Draft an issue, triage a whole queue at once, reply to review comments, close and reopen.</p>
    </div>
    <div data-reveal data-stagger="1">
      <h3>Releases</h3>
      <p>Raw commits turned into release notes, with Conventional Commit messages and branch names.</p>
    </div>
    <div data-reveal data-stagger="1">
      <h3>Scoping</h3>
      <p>Off-topic requests are refused before they reach the model, not after the answer comes back.</p>
    </div>
  </div>
</section>

<section class="section section-rule">
  <div class="section-head" data-reveal>
    <p class="eyebrow">How it works</p>
    <h2>Four steps, then you never touch the website again</h2>
    <p>
      The token decides what it can reach. Nothing else about your account is
      touched, and every write is confirmed before it happens.
    </p>
  </div>
  <div class="steps">
    <div class="step" data-reveal data-stagger="1">
      <div>
        <h3>Connect a token</h3>
        <p>A fine-grained personal access token. Encrypted with Windows DPAPI the moment you paste it, and readable by nothing but this app on your account.</p>
      </div>
    </div>
    <div class="step" data-reveal data-stagger="1">
      <div>
        <h3>Point it at a model</h3>
        <p>Any OpenAI-compatible endpoint — OpenAI, OpenRouter, Groq, Together, Ollama, LM Studio. A local model needs no key and the app works offline.</p>
      </div>
    </div>
    <div class="step" data-reveal data-stagger="1">
      <div>
        <h3>Ask for the work</h3>
        <p>Write a README, triage the issue queue, turn forty commits into release notes. The model sees the repository, not a guess about it.</p>
      </div>
    </div>
    <div class="step" data-reveal data-stagger="1">
      <div>
        <h3>Review, then commit</h3>
        <p>Every write shows you the file, the branch and the message first. Nothing lands on GitHub that you have not seen.</p>
      </div>
    </div>
  </div>
</section>

<section class="section section-rule">
  <div class="section-head" data-reveal>
    <p class="eyebrow">The assistant's boundary</p>
    <h2>It will not answer anything that is not about GitHub</h2>
    <p>
      Not a preference — an enforcement. The request is classified before it is
      sent, so a question about recipes or share prices never costs you a token
      and never comes back with a confident wrong answer.
    </p>
  </div>
  <div class="bento">
    <div data-reveal data-stagger="1">
      <span class="bento-num">Layer 01</span>
      <h3>Before the request</h3>
      <p>The prompt is classified on your machine. Off-topic and it is dropped there.</p>
    </div>
    <div data-reveal data-stagger="1">
      <span class="bento-num">Layer 02</span>
      <h3>In the system prompt</h3>
      <p>The model is told the boundary in the same words every time, so it does not drift.</p>
    </div>
    <div data-reveal data-stagger="1">
      <span class="bento-num">Layer 03</span>
      <h3>On the answer</h3>
      <p>What comes back is checked too. A refusal is shown as a refusal, not as a blank.</p>
    </div>
  </div>
</section>

<section class="section section-rule">
  <div class="facts">
    <div class="fact" data-reveal data-stagger="1">
      <b data-count="63" data-count-suffix=" MB">63 MB</b>
      <span>One file, no installer, no runtime</span>
    </div>
    <div class="fact" data-reveal data-stagger="1">
      <b data-count="10">10</b>
      <span>Pages covering the whole of GitHub</span>
    </div>
    <div class="fact" data-reveal data-stagger="1">
      <b data-count="0">0</b>
      <span>Telemetry, analytics or crash reporting</span>
    </div>
    <div class="fact" data-reveal data-stagger="1">
      <b data-count="2">2</b>
      <span>Hosts it will ever talk to: GitHub and your model</span>
    </div>
  </div>
</section>

<section class="section section-rule">
  <div class="section-head" data-reveal>
    <p class="eyebrow">What it will not do</p>
    <h2>Said plainly, so you are not looking for it</h2>
    <p>
      The scope limit is a feature. These limits are the same kind of thing —
      stated rather than discovered.
    </p>
  </div>
  <div class="callout" data-reveal>
    <p>
      <span class="pill pill-ok">Scope enforced before sending</span>
      <span class="pill">Runs offline with a local model</span>
      <span class="pill">No telemetry</span>
    </p>
    <p>
      It will not manage SSH keys, create OAuth apps, or edit webhooks — a hook
      you added here would start firing at a server you do not control.
    </p>
  </div>
  <div class="cta-row" data-reveal>
    <a class="btn btn-primary" href="https://github.com/mrlurix/github-manager/releases/latest">
      Download for Windows <span class="btn-arrow" aria-hidden="true"></span>
    </a>
    <a class="btn btn-solid" href="features.html">
      Read the features <span class="btn-arrow" aria-hidden="true"></span>
    </a>
  </div>
</section>

</div>