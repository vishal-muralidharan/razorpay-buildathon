---
name: project-readme
description: Write or refresh a project README and the GitHub repository description, homepage, and topics. Use when the user asks for a README, a better README, a repo description, GitHub topics, a catchy project page, or to make the repository look good to visitors.
compatibility: Needs file read, file edit, shell, git, and Python 3. The gh CLI is optional and only the user runs it.
---

# Project README

Writes a README that sells the project and stays true to the code, plus the GitHub description, homepage, and topics. The style depends on the kind of project.

Scripts live in `.agents/skills/project-readme/scripts/`. If python3 is not found, use python or py -3.

## Read first

- `.agents/project-profile.yaml` for name, summary, stack, and commands.
- `.agents/blueprints/` for real features, data, auth, and UI facts, if the folder exists.
- `references/styles.md` for the 4 styles and how to pick one.
- `references/github-rules.md` for GitHub limits and Markdown rules.

## Steps

1. Collect facts. Never invent a feature, a command, a link, or a number.
   ```bash
   python3 .agents/skills/project-readme/scripts/readme_facts.py --root .
   ```
   It prints JSON: name, summary, stack, commands, scripts, license, homepage, repo, screenshots, community files, the existing README headings, a suggested style with the reason, and suggested topics.

2. Pick the style. Use `suggested_style` unless the user asked for another one. Tell the user the style and the reason in 1 line. Styles: `technical`, `showcase`, `minimal`, `api`.

3. Draft the README from `assets/templates/<style>.md`.
   - Fill every section from the facts. A fact you cannot find becomes `TODO: <what is missing>`, never a guess.
   - Copy commands from the facts (`commands` or `scripts`), with the project's package manager.
   - Features come from blueprints, routes, components, and the profile summary. Describe what a user can do, not how the code is built.
   - If a README exists, keep every section the user wrote by hand. Rewrite only what the facts contradict, and say what changed.

4. Write `.agents/repo-meta.yaml`:
   ```yaml
   style: showcase
   description: "One sentence pitch, 350 characters or fewer."
   homepage: "https://example.com"
   topics: [react, vite, expense-tracker]
   ```
   Topics: lowercase letters, digits, and hyphens, 50 characters each, 20 at most. Leave `homepage` empty when there is no live site.

5. Check the result. Fix every ERROR. Resolve every TODO, or tell the user which facts are missing.
   ```bash
   python3 .agents/skills/project-readme/scripts/check_readme.py --root .
   ```

6. Show the user the README diff and the repo meta. Wait for approval before committing.

7. Commit `README.md` and `.agents/repo-meta.yaml` with the atomic-commits skill.

8. Print the GitHub settings commands for the user to run. Never run them yourself.
   ```bash
   python3 .agents/skills/project-readme/scripts/check_readme.py --root . --print-gh
   ```

## Rules

- Facts only. Every claim in the README must trace to the code, the profile, the blueprints, or the user.
- The first screen matters: title, a 1 or 2 sentence pitch, and a demo link or screenshot when one exists.
- Match the style. No emojis in `technical` or `api` headings. In `showcase`, 1 emoji per feature line, used the same way throughout.
- Never paste secrets, tokens, keys, or values from `.env` files. Name variables only, from `.env.example`.
- Never change GitHub settings, push, or publish. The user runs the printed `gh` commands.
- Keep the README in the project root unless the profile sets `docs.readme` to another path.
