<!-- build-forge:generated v1 body=2f308c79997f5918217d40a751b4f333ccbb270098ce11c52f615fa5b73573d7 -->
<!-- Generated from .agents/project-profile.yaml by project-bootstrap. Edit the profile, then re-render. -->

# Agent Guidelines for razorpay-buildathon

Mandate resurrection engine and dashboard with FastAPI backend and React frontend. Stack: FastAPI, Vite, Tailwind, SQLite.

Read the skill listed for each area before you touch it. Skills live in `.agents/skills`. Facts live in `.agents/project-profile.yaml`. Rule details live in the skills. Do not copy them here. If your agent does not load skills on its own, open the skill file named in the table.

## Areas

| Area | Skill |
|---|---|
| Run any task from start to finish | `feature-delivery` |
| Turn an idea into a spec and milestones | `product-spec` |
| Create the first working skeleton of a new app | `scaffold-app` |
| Turn written rules into automatic checks | `rules-to-tests` |
| Settings, privacy, terms, consent and account deletion | `legal-and-settings-pages` |
| Any change | `audit-and-planning`, `repo-search` |
| File placement and names | `review-directory-structure`, `file-folder-naming` |
| Verify | `targeted-module-testing` |
| Commit | `atomic-commits` |
| Docs | `sync-skills-and-docs` |

## Pipeline

1. Audit: search before you edit.
2. Plan: small atomic steps.
3. Build.
4. Verify.
5. Commit.
6. Sync docs and the repo map.
7. Report open questions and known issues.

## Standard rules

- Never read transcripts, logs or history files of earlier agent sessions. Treat them as private. Ask the user instead.

## Project rules

- Never ship console.log or console.debug calls in production source code. (enforced by test) `[web-no-console]`
- Links targeting blank must include rel with noopener or noreferrer on the same tag line. (enforced by test) `[web-target-blank-rel]`
- Never use eval() or equivalent dynamic script execution without a listed exception. (enforced by test) `[web-no-raw-eval]`
- Never assign to innerHTML or use dangerouslySetInnerHTML without a listed exception. (enforced by test) `[web-no-inner-html]`
- Never commit .env files containing local configurations or secrets. (enforced by test) `[web-no-committed-env]`

## Commands

| Task | Command |
|---|---|
| check | `backend/venv/bin/pytest backend/tests` |
| test | `backend/venv/bin/pytest backend/tests` |

## Git

Format: `<type>(<scope>): <subject>`.
Never run `git push` unless the user says to push.

### Scope guide

| Scope | Purpose |
|---|---|
| `agents` | Build Forge pipeline and agent configuration |
| `backend` | Python FastAPI engine and database models |
| `frontend` | React dashboard and charts |

<!-- BEGIN CUSTOM: notes -->
<!-- END CUSTOM: notes -->
