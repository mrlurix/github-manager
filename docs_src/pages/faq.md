---
title: FAQ
description: Common questions about tokens, privacy, the app's limits and troubleshooting.
---

## Tokens and access

### Why a token rather than signing in?

The app deliberately does not use OAuth. OAuth needs a registered client and a
browser round trip, which does not fit "a single portable exe". A Personal
Access Token is simpler and more transparent: you decide what it can do, and
when to revoke it.

### Does the app phone anywhere unexpected?

Only two places, both configurable in Settings:

- The GitHub API — `api.github.com`
- Whichever AI provider you chose

If you pick a local model, traffic stays between your machine and `localhost`.

### What if my token leaks?

Delete it on [github.com/settings/tokens](https://github.com/settings/tokens).
It stops working immediately and the app stops using it.

## Privacy

### Where does my repository content go?

Only where you send it. When you ask the AI for something, the file tree and a
few key files are sent to the model — but that only happens when you press the
button, never automatically.

### Does GitHub store my access?

Not remotely, in fact: your token is stored only on your own machine, encrypted.
There is no server in the middle. This app talks to GitHub, not to anyone else.

### What does the app store?

```text
data/
  settings.json     appearance and AI settings
  secrets.json      token and API key, encrypted with DPAPI
```

That is all. No logs, no analytics, no crash reporting.

### Can I keep the data folder on a USB stick?

Yes — that is exactly what it is designed for. The `data` folder stays next to
the executable and travels with it.

## Limits

### Why is there no GitHub Enterprise setting?

The client can be pointed at a different API root and the tests cover that, but
there is no field for it in the UI yet. It is a small change if you need it.

### Why no graphs?

GitHub traffic analytics live behind a separate account, and they have nothing to
do with the core workflow. Deliberately left out.

### Can it create API tokens for me?

No. Creating one needs two-factor re-authentication in a browser, so the app
sends you to the token page instead of pretending it can do it.

### Does it work offline?

Only with a local model. The GitHub side needs a network because nothing is
cached — and that is on purpose, so you never see a stale view of a repository.

### How many repositories can it see?

Up to 600, fetched page by page. With more than that you will see part of the
list.

## Troubleshooting

### The AI buttons are greyed out

The AI provider is not configured. Go to **Settings → AI** and pick a provider.
Ollama and LM Studio need no key — just the model, then **Test connection**.

### The README comes back empty

Expected if the repository has no README yet. Use **Generate README** to create
one, or **Load existing** to check the path is right.

### I got a 403 rate limit error

Your hourly GitHub quota is spent. The app tells you roughly when it resets. It
deliberately does not retry, because waiting a few seconds cannot help and would
only freeze the interface.

### The interface looks wrong

Set Windows display scaling to 100%, or nudge **Settings → UI scale** up or down.

### Nothing happens after I press commit

The request is probably still running. A GitHub call can take a while. If it
fails you get a message at the bottom of the page.

## Contributing

The repository is open. If you find a problem or a missing feature:

1. Open an issue
2. Send a pull request if you like

Run the tests before you push:

```bash
python tests/run_all_tests.py
```

All nine suites should be green.

## Licence

MIT. See [LICENSE](https://github.com/mrlurix/github-manager/blob/main/LICENSE)
in the repository.