# Review Changes Workflow

Use this workflow when auditing a pull request, branch diff, or uncommitted changes in a project with a profile.

## When to use

- User asks for a code review or diff audit.
- Pull request or branch diff needs verification against project rules.
- Pre-merge check to verify data invariants and design tokens.

## Stages with gates

1. **Stage 1: Read the diff**
   - Run `git diff` or `git diff main...HEAD`.
   - Identify all added, modified, and removed files and lines.
   - Gate: Complete list of touched files and line ranges identified.

2. **Stage 2: Profile rules and checks audit**
   - Check the diff against all rules in `.agents/project-profile.yaml`.
   - Check if automated rule checks in `.agents/checks/` pass.
   - Gate: Every rule violation identified with exact rule ID.

3. **Stage 3: Protected data and blueprints check**
   - Check if any item in `data.protected` was touched.
   - Verify design tokens against `.agents/blueprints/tokens.md` or `design.tokens_file`.
   - Verify database structures against `.agents/blueprints/data.md` or `data.schema_source`.
   - Gate: Any unauthorized protected data modification flagged as a blocker.

4. **Stage 4: Automated check verification**
   - Run `commands.check` to evaluate tests, linting, and build integrity.
   - Gate: Check results recorded with exit code.

5. **Stage 5: Report findings**
   - Group findings by severity: Blocker, Warning, Note.
   - Include file:line citations for every finding.
   - Gate: Review report written. 0 source files modified.

## What to read

- Working diff from git: `git diff HEAD` or `git diff <base>...<head>`.
- `.agents/project-profile.yaml`: Rules, protected data, and commands.
- `.agents/blueprints/` when present on disk.
- Test and lint output from `commands.check`.

## What to produce

- Structured code review report containing:
  - Summary of changed files and overall impact.
  - Blockers: Rule violations, security risks, broken invariants, failing checks.
  - Warnings: Missing test coverage, performance concerns, styling inconsistencies.
  - Notes: Documentation improvements or non-blocking suggestions.
- Each finding includes `file:line` citation, rule ID, and suggested remedy.
- Edit nothing unless explicitly asked by the user.

## Stop conditions

- Security vulnerability or exposed credential detected in diff: flag immediately as a critical blocker.
- Protected data modified without documented user authorization: flag immediately as a blocker.
- Do not edit files during review unless the user explicitly requests automatic fixes.
