---
title: Features
description: A complete tour of GitHub Manager — README Studio, repositories, issues and pull requests, releases, account and settings.
---

The app has ten pages. This one covers each of them.

## Map of the app

| Page | What it is for |
| --- | --- |
| Welcome | Connect a token and get oriented |
| Dashboard | Account overview, recent activity and shortcuts |
| README Studio | Write and commit READMEs and the supporting files |
| Repositories | Full management of your repositories |
| Repository | What is inside one repository: files, branches, tags, collaborators, webhooks |
| Issues & PRs | Work through issues and pull requests |
| Releases & commits | Release notes, commit messages, branch names |
| AI Assistant | Free-form chat, scoped strictly to GitHub |
| Account | Profile, bio, avatar and organisations |
| Settings | Appearance, AI provider and data |

---

## README Studio

The centre of the app. Two panes: the editor on the right, a live preview on the
left.

### Generation settings

Tell the AI what to write before it writes it:

- **Tone** — professional, friendly, minimal, detailed, playful or enterprise
- **Language** — English, Persian, Spanish, French, German, Turkish, Arabic, Hindi or Portuguese
- **Audience** — developers, beginners, teams, open source contributors, product managers or students
- **Creativity** — a number between 0 (precise) and 1 (free)
- **Sections** — toggle each one individually: header and badges, description, features, tech stack, installation, usage, screenshots, contributing, licence, roadmap
- **Extra instructions** — anything else, for example "add a Docker section and a CLI usage example"

### The output

The model sees the real repository: the file tree, the languages in use, the
topics, the current README and a few key files. The result is about your project
rather than generic filler.

### Refine and review

- **Refine** — write "make the intro clearer" and the same document is rewritten
- **Review** — a full preview with copy-to-clipboard and save-to-disk
- **Draft extra file** — ready-made templates for CONTRIBUTING, LICENSE, `.gitignore`, SECURITY, CODE_OF_CONDUCT and CHANGELOG

### Writing to GitHub

- **Commit to GitHub** — you see the file, the branch and the commit message before confirming
- **Save .md** — write to disk without touching GitHub
- **Load existing** — pull the current README back down from the server

> If the repository has no README yet, one is created. If it does, the file's
> `sha` is read first so the update is applied to the right version instead of
> blindly overwriting whatever happens to be there.

---

## Repositories

### The list

Search by name and description, filter by private/public and archived, and pick
one of three layouts: compact, comfortable or cards.

### Actions

| Action | Notes |
| --- | --- |
| Create | Name, description, homepage, topics, visibility, an initial README and a licence template, plus any files you attach |
| Edit | Name, description, homepage, topics, default branch and archived state, plus adding and deleting files |
| Upload files | Commit one or more files from disk, to any folder and any branch |
| Archive | Reversible and safe; nothing is deleted |
| Delete | You must type the full repository name to confirm |
| Fork | Creates the fork immediately |
| Star | Adds or removes the star |

### Uploading files

Use **Upload files…** on a repository card, or the ⋮ menu beside it.

- Pick one file or several; each row shows its size
- **Folder** puts them all under a directory in the repository — change it and
  the whole batch moves, while any path you edited by hand stays put
- Each row is editable, so a file can be renamed or moved without leaving the dialog
- Choose whether an existing file may be overwritten, or the upload stops
- Commit message and branch are yours to set

> GitHub commits one file per request, so a batch is a sequence. Each file is
> confirmed as it lands, and a failure stops the rest rather than leaving you
> guessing how far it got. Binary files are uploaded byte for byte.

### Files in the create and edit dialogs

The same picker is built into both, so a repository can be seeded or tidied
without opening a second dialog.

- **Create repository** — attach files while creating. They are committed
  straight after the repository is made, since the API takes no file content in
  the create call itself
- **Edit repository** — the current files are listed with their sizes; tick one
  to delete it, and add new files in the section below

Deletions are applied before uploads, so a path that is removed and re-added
somewhere else cannot be clobbered by the order the requests happen to land in.
Marking the same path for both is refused rather than resolved silently.

> An archived repository is read only, so the file section is not offered there.

### AI suggestions

"Describe with AI" reads the whole repository and proposes a one-line
description plus a set of topics. Nothing is sent to GitHub until you press
Apply.

---

## Repository

The Repositories page manages *your* repositories — creating them, editing their
settings, archiving them. This page looks *inside* a single one. Pick a
repository and a branch at the top, and everything below follows that choice.

### Files

- The tree is built from the real paths on the selected branch, folders nested
  as they are in the repository
- **Filter by path** narrows it as you type, so a large repository stays navigable
- Selecting a file reads it from GitHub and shows the contents beside the tree
- **Upload** sends you to the same upload dialog used everywhere else, so a file
  added here behaves exactly like one added from a repository card

### Branches

- Every branch on the repository, with the one you are currently viewing marked
- Type a name and **Create** — it is branched from whatever branch you have
  selected, not from the repository default, which is usually what you want when
  you are working in a feature branch
- Double-clicking a branch switches the whole page to it

### Tags

Every tag with the commit it points at, newest first by name. The commit is
shortened to twelve characters, which is enough to identify it in any Git
client.

### Collaborators

- Each person with the highest permission they actually hold — `admin`, `maintain`,
  `write`, `triage` or `read`
- Add someone by username and pick their level
- Removing someone asks first, because access is lost the moment it is applied

### Webhooks

Read-only, and said so on the tab. Each hook is listed with the events it fires
on, and its target URL is in the tooltip. Hooks are created on GitHub rather
than here, since a misconfigured one fires at someone else's server.

> Every list on this page is loaded on its own, when you switch to the tab that
> needs it. Opening the page costs one request, not five.

---

## Issues & pull requests

### List and detail

- Toggle between issues and pull requests, and between open, closed and all
- Each row shows the number, title, author, comment count and labels
- The detail pane renders the issue body and every comment with its author

### Actions

| Action | Notes |
| --- | --- |
| Draft issue | Write a sentence or two; the AI expands it into a structured issue with steps and expected behaviour |
| AI reply | Drafted from the issue body and the existing comments, editable before it is posted |
| AI triage | Reviews the whole queue at once and suggests a type, a priority and a next action for each |
| Close / reopen | Changes state, with confirmation |

> The selection survives a refresh. Post a reply, and you are still looking at
> the same issue when you get back, so the next action lands where you expect.

---

## Releases & commits

### Lists

Commits and releases sit side by side, each loadable on its own.

### Release notes

- **Generate notes** — takes the commit list and writes release notes, streamed token by token as they arrive
- **Publish** — confirmed with a dialog naming the tag and repository
- **New release** — create one by hand with your own tag, name and body

The tag field is pre-filled from the newest release: if the latest is `v1.2.0` it
suggests `v1.3.0`.

### Commit messages and branch names

- **Write commit message** — describe the change in plain language and get a Conventional Commit with a subject, a wrapped body and a BREAKING CHANGE footer when one is needed
- **Suggest branch** — the same description yields a `feat/…` style branch name
- **Create branch** — creates it on GitHub

Three styles are supported: Conventional Commits, plain imperative and Angular.

---

## AI Assistant

Free-form chat, with four things worth knowing.

### Scoped to GitHub

Three independent layers:

1. **Before sending** — the request is classified. Anything off-topic never reaches the model.
2. **In the system prompt** — the model is given an explicit allow and deny list.
3. **After the answer** — the response is validated too, and replaced with an out-of-scope notice if it strayed.

### Repository context

With "Attach repo context" on, the selected repository's structure and contents
are included so answers are about your project.

### Streaming

Responses appear token by token, with Enter to send.

### Shortcuts

Six ready-made prompts: write a README, suggest topics, draft a CI workflow,
review your current README, write a `.gitignore`, and explain adding a LICENSE.

---

## Account

- **Profile** — name, company, location, website, Twitter handle and public email
- **Bio** — write it yourself, have the AI improve it, or pick from several finished options
- **Avatar** — upload a PNG, JPEG, GIF or WebP; type and file size are checked before anything is sent
- **Organisations** — the organisations you have access to
- **Profile README** — creates or updates the `<username>/<username>` repository
- **Activity** — recent GitHub events

---

## Settings

### Appearance

- Dark and light themes
- Six accent colours: violet, blue, emerald, amber, rose and cyan
- Font family
- UI scale from 85% to 130%

### AI

- Provider from the list, or any OpenAI compatible address
- Model, temperature, max tokens and timeout
- Streaming on or off
- List the models the provider offers
- Test the connection

### Data

- Where the data folder is
- Clear the API key
- **Erase everything** — tokens, keys, the repository cache and settings

---

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| `Ctrl+1` … `Ctrl+9` | Jump to a page, in the order shown in the sidebar |
| `Ctrl+K` | AI Assistant |
| `Ctrl+,` | Settings |
| `Ctrl+R` | Refresh the current page |
| `Ctrl+N` | New repository |
| `Ctrl+B` | Collapse or expand the sidebar |
| `Ctrl+Shift+R` | Toggle dark and light |
| `Ctrl+Q` | Quit |

---

## What is not here

Stated plainly, so you are not looking for it:

- **No GitHub Enterprise setting in the UI** — the client can be pointed at another host, but there is no field for it yet
- **No SSH key or API key management** — creating a token needs re-authentication in a browser, so it is deliberately left out
- **No domain-level analytics** — GitHub traffic graphs are not shown
- **No webhooks are created or edited** — the Repository page lists them, but a hook you add here would start firing at a server you may not control
- **No offline mode** — nothing is cached, so the app will not show you stale repository data