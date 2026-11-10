# Blueprint format specification

Blueprints provide verified, compact, and structured facts about the codebase.

## Directory layout

Generated in the project root under `.agents/blueprints/`:
```text
.agents/blueprints/
├── index.md             # Blueprint index (maximum 60 lines)
├── manifest.json        # Deterministic file hashes and analyzer metadata
├── candidates.md        # Extracted candidate rules for confirmation
├── data.md              # Database schemas, storage keys, data models
├── tokens.md            # CSS and theme design tokens
├── ui.md                # UI component catalog and state primitives
├── layout.md            # Breakpoints, shell layout, and mobile rules
├── auth.md              # Auth providers, guards, and logout cleanup
└── config.md            # Environment variable names and route mappings
```

## File format

Every blueprint file follows this structure:

```markdown
# Area Blueprint

Brief area summary.

## Generated facts

- Item name
  - Evidence: `src/path/to/file.ts:42` (confidence: high)
  - Detail: short signature or property summary (12 lines or fewer)

<!-- BEGIN CUSTOM: contracts -->
Human-written facts that no analyzer can derive (e.g. payload shapes, state machines, UX contracts).
Rules never go here. Rules belong in the profile.
<!-- END CUSTOM: contracts -->
```

## Line budgets and overflow

- `index.md`: 60 lines or fewer.
- Generated section: 250 lines or fewer per file.
- If an area exceeds 250 generated lines, the generator splits it into `<area>-part-2.md`, `<area>-part-3.md`, and links each part from `index.md`.

## Evidence and confidence

Every fact must list:
1. Exact file and line: `path/to/file.ext:line`.
2. Confidence level:
   - `high`: Directly declared typed interface, SQL schema, or explicit token.
   - `medium`: Inferred component prop or pattern match.
   - `low`: Heuristic match.
3. If an analyzer cannot determine a fact, write `unknown`. Never guess.

## Contract evidence anchors

Human-written facts inside `<!-- BEGIN CUSTOM: contracts -->` can specify evidence anchors:
```markdown
- Payment session payload shape
  Evidence: `src/api/payment.ts:42` contains: `PaymentSessionResponse`
```
When `blueprint.py drift` runs:
1. It verifies that `src/api/payment.ts` exists.
2. If `contains:` is provided, it verifies that the text `PaymentSessionResponse` appears within 5 lines of line 42.

## Blueprint lifecycle commands

- `init`: Scaffolds missing canonical blueprint files (`data`, `tokens`, `ui`, `layout`, `auth`, `config`) from templates without overwriting existing files.
- `extract`: Analyzes codebase facts and rewrites the generated portions of blueprint files, preserving custom blocks.
- `adopt`: Moves an over-limit custom block out of a convention skill into blueprint contracts and replaces it with a `show` pointer.
- `link-check`: Verifies convention skills link to existing blueprints, `index.md` lists all files, and skill custom blocks are under 80 lines.
- `drift`: Runs verify, stale, link-check, and contract evidence anchor validation.
- `verify`: Confirms all evidence references point to existing files and valid line numbers.
- `stale`: Checks whether any source files changed since extraction.
- `show`: Queries facts for touched paths within a specified line budget.
- `candidates`: Lists candidate rules extracted from codebase patterns for user confirmation.

## Determinism and hashing

- Content uses LF line endings.
- All lists, tables, and dictionary keys are sorted alphabetically.
- No timestamps appear in generated blueprint files.
- `manifest.json` stores LF-normalized SHA-256 hashes of every source file analyzed.

## Secret safety

- Blueprints never read `.env` or files named like secrets.
- Environment variable names are collected from source code (`process.env.VAR`, `import.meta.env.VAR`) or `.env.example`.
- Values are never saved.
- Secret patterns (API keys, private keys, tokens) are scanned before writing. Extraction aborts if a secret pattern matches.
