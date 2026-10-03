---
title: AI
description: Choosing a provider, configuring a model, running a local model, and how the GitHub-only scope limit works.
---

Every AI feature in the app goes through one thin layer. That layer builds a
prompt, sends it, and hands back the answer. So you can swap in any
OpenAI-compatible service and everything keeps working.

## Supported providers

| Provider | Default address | API key |
| --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | yes |
| OpenRouter | `https://openrouter.ai/api/v1` | yes |
| Groq | `https://api.groq.com/openai/v1` | yes |
| Together | `https://api.together.xyz/v1` | yes |
| Ollama | `http://localhost:11434/v1` | **no** |
| LM Studio | `http://localhost:1234/v1` | **no** |
| Custom | any address you like | depends on the service |

## A local model for fully offline use

If nothing should leave your machine, this is the way.

### Ollama

```bash
ollama pull llama3.1
ollama pull qwen2.5
```

Then in the app:

1. Set the provider to **Ollama**
2. Use the model name exactly as you pulled it, for example `llama3.1`
3. Leave the API key **empty**
4. Click **Test connection**

### LM Studio

1. Download a model in LM Studio and load it
2. Start the local server
3. Set the provider to **LM Studio** and click **Test connection**

> A local model still knows plenty of general things, but being scoped to
> GitHub usually makes it weaker than the large hosted ones. For structured work
> like writing a README it is entirely adequate.

## Suggested settings

| Setting | Suggested | Why |
| --- | --- | --- |
| Temperature | 0.6 | For technical writing, balances creativity and accuracy |
| Max tokens | 2000 | A complete README fits |
| Timeout | 120 s | Local models are slower |
| Streaming | on | You see the answer immediately |

For structured output such as JSON, drop the temperature to 0.2–0.4 so results
stay consistent.

## The limits on the assistant

This is a feature, not a restriction the app could not overcome. The assistant is
**deliberately** limited to GitHub.

### What it will do

- Write and improve READMEs, profile READMEs and documentation
- Repository settings, topics, visibility, releases and tags
- Issues and pull requests: drafting, triage, review replies
- Commits, branch names, merge and rebase questions
- GitHub Actions workflows, `.gitignore`, licences, security and tokens
- Read code and suggest a project structure

### What it will not do

- Anything outside GitHub: recipes, medical advice, legal or financial questions, general tutoring
- Writing code for targets unrelated to a GitHub repository
- Working around GitHub's own limits

### How the limit is enforced

Three independent layers, one after another:

1. **Classified before sending.** The request is checked. If it is off-topic it
   never reaches the model, and you get an out-of-scope reply.
2. **System prompt.** An explicit allow and deny list travels with every request.
3. **Output validated.** The answer is checked too. If it strayed, it is
   replaced with the refusal message.

The first layer also blunts **prompt injection**: if a README or an issue
contains "ignore all previous instructions", that text arrives as content rather
than as a command, and the repository context is always placed after the scope
reminder.

> These layers are not an absolute guarantee; no text filter is. What they do is
> make the failure unlikely and the consequences small.

## What is sent to the model

Only when you ask for it:

- The repository name and description
- The file tree
- The languages used and the topics
- The current README
- A few key files, capped in size
- The issue or comment you are working on

**Never sent:** your GitHub token, your API key, local file paths, or anything in
the `data` folder.

The `app/core/` package deliberately imports nothing from Qt, which is what makes
the logic testable on its own — and what lets the integration suite drive the
real client over real HTTP.

## When it does not work

| Symptom | Likely cause |
| --- | --- |
| "Could not reach the provider" | Wrong address, or the service is not running |
| "AI provider error 401" | Wrong or expired key |
| Empty answers | Model too small, or parameters out of range |
| Irrelevant answers | Weak local model, or a rate-limited cloud service |
| Cuts out mid-answer | Raise the timeout in Settings |