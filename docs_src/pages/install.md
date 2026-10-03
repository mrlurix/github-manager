---
title: Getting started
description: Download GitHub Manager, create a token, connect, and be writing READMEs in three minutes.
---

## Download

Grab `GitHubManager.exe` from the
[releases page](https://github.com/mrlurix/github-manager/releases/latest).

- About 63 MB
- A single file, no installer
- Runs on 64-bit Windows

Put it wherever you like — `C:\Tools`, a desktop folder, a USB stick. Nothing is
written to Program Files and no administrator rights are needed.

> The exe is unsigned, so SmartScreen may warn that the publisher is unknown.
> Choose **More info → Run anyway**. Every app without a commercial certificate
> gets this.

## Create a token

The app needs a **Personal Access Token**.

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Choose **Generate new token → Fine-grained**
3. Grant only what the app actually uses:
   - `Contents: Read and write` — to commit READMEs and other files
   - `Issues: Read and write` — to work with issues
   - `Pull requests: Read and write` — to work with pull requests
   - `Metadata: Read-only` — added automatically
4. Restrict it to the repositories you actually want to touch
5. Generate and copy it — **it is shown only once**

Classic tokens work too; they need the `repo` and `delete_repo` scopes. Skip
`delete_repo` unless you intend to delete repositories — everything else works
without it.

## First run

1. Open the app
2. Click **Connect GitHub**
3. Paste the token and confirm

The token is encrypted with **Windows DPAPI** immediately and stored in the
`data` folder next to the executable. Another user on the same machine cannot
decrypt it.

If that folder is not writable — inside Program Files, say — the app falls back
to your user data folder automatically.

## Configure the AI

Next step is picking a provider:

1. Open **Settings → AI**
2. Choose a provider
3. Enter an API key if it is a cloud service
4. Click **Test connection**

If you run a model locally, pick `Ollama` — **no API key is needed** and the
whole app works offline.

## Where to start

| You want to… | Start here |
| --- | --- |
| Write a README | README Studio → pick a repository → **Generate README** |
| Tidy up issues | Issues & PRs → **AI triage** |
| Ship a release | Releases & commits → **Load commits** → **Generate notes** |
| Ask a question | Press **Ctrl+K** and just ask |

## Updating

Download the new exe from the releases page and replace the old one. The `data`
folder is left alone, so your token and settings survive.

## If something does not work

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| "Invalid or expired token" | Token expired or missing scopes | Create a new one and check the scopes |
| "Not found, or the token lacks access" | No access to that repository | Make sure the repository is selected when creating the token |
| "API rate limit exceeded" | Hourly quota spent | The error names roughly when it resets; wait |
| "Access denied" | Writing to a protected repository | That is GitHub's own rule |
| AI buttons are greyed out | No provider configured | Finish the AI settings |
| The app will not open | Antivirus, or an old Windows build | Unblock the file, or update Windows |

## Running from source

To run or modify it yourself, see [Building from source](build.html).

```bash
git clone https://github.com/mrlurix/github-manager.git
cd github-manager
pip install -r requirements.txt
python main.py
```

On Windows you can just run `run.bat`.