# Spec template

Copy this structure into `docs/product-spec.md`. Delete sections that do not apply. Keep the whole file under 2 pages.

```markdown
# <App name>

<One sentence: what it does and for whom.>

## Problem

<What people do today and why it falls short. 2 or 3 sentences.>

## Users

- <Primary user: who they are and the moment they open the app.>
- <Secondary user, if any.>

## Core flows

1. <Flow name>: <steps in 1 or 2 lines. Start: what the user sees. End: what changed.>
2. <Flow name>: ...
3. <Flow name>: ...

## Data

| Entity | Fields the flows need | Stored where |
|---|---|---|
| <Entity> | <field, field, field> | <device, server, both> |

Data rules that must never break:
- <rule>

## Platform and constraints

- Platform: <web, installable web app, desktop, mobile, command line, API>
- Accounts: <none, optional, required>
- Offline: <not needed, nice to have, required>
- ASSUMPTION: <anything guessed>

## Non-goals (version 1)

- <not doing this>
- <not doing this>
- <not doing this>

## Milestones

### Milestone 1: <name>. The user can <outcome>.

Build steps:
1. <one functional unit>. Proof: <how we know it works>
2. ...

### Milestone 2: <name>. The user can <outcome>.

(Steps are drafted when milestone 1 ships.)

## Open questions

- <question for the user>
```
