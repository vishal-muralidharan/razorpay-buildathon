# README styles

Pick 1 style per project. `readme_facts.py` suggests one with a reason. The user can override it.

| Style | Use for | Tone | Emojis |
|---|---|---|---|
| `technical` | CLIs, libraries, frameworks, developer tools | Precise, complete, scannable | None in headings. Status badges are fine. |
| `showcase` | Apps people use: web apps, mobile apps, extensions | Friendly, visual, benefit first | 1 per feature line, same pattern throughout |
| `minimal` | Small static sites, portfolios, experiments | Short and clear | Optional, a few at most |
| `api` | Backends and services without their own UI | Exact and contract focused | None in headings |

## How the suggestion works

- A `bin` entry, or a package with `main` or `exports` and no UI framework: `technical`.
- A UI framework (React, Vue, Svelte, Next, Angular, Solid) or a browser extension manifest: `showcase`.
- A backend framework (FastAPI, Flask, Django, Express, Nest, Hono) and no UI: `api`.
- An `index.html` at the root and no package manager: `minimal`.
- A repo with both a UI and a backend: `showcase`, with an API section.

## Sections per style

`check_readme.py` requires the sections marked required. Heading text can vary. The check ignores emojis and case.

- `technical`: Install (required), Usage or Quick start (required), Requirements or Compatibility (required), Configuration, Commands or CLI reference, Contributing, License (required).
- `showcase`: Features (required), Getting started or Run locally (required), Tech stack or Built with (required), Screenshots or Demo, Roadmap, License.
- `minimal`: a title and a 1 or 2 sentence summary (required), then what to look at and how to run it.
- `api`: Endpoints or API (required), Setup or Getting started (required), Environment or Configuration (required), Error format, License.

## Writing rules for every style

- Lead with the value for the reader, then the how.
- Short paragraphs, 1 idea each. Lists for features and steps.
- Every command in a fenced code block, copied from the real scripts.
- Screenshots with descriptive alt text and relative paths into the repo.
- Name environment variables from `.env.example`. Never show values.
- Link the license file instead of restating it.

## Showcase emoji pattern

Put 1 emoji at the start of each feature line, chosen for meaning, not decoration:

```markdown
## Features

- 💸 **Track spending** in seconds, with categories you control.
- 📊 **See where money goes** with monthly charts.
- 🔒 **Private by default.** Your data stays in your account.
```

Keep emojis out of commands, code blocks, and table headers.
