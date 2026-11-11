# Release Preparation Workflow

Use this workflow when preparing a release, proposing a version bump, or updating changelogs before tagging.

## When to use

- User asks to prepare a release, bump the version, or draft release notes.
- Feature milestone completed and ready for tagging.
- Preparing package distribution.

## Stages with gates

1. **Stage 1: Verify clean state and checks**
   - Check `git status` to confirm working tree is clean.
   - Run `commands.check` to confirm all tests and builds pass.
   - Gate: Working tree is clean and `commands.check` exits 0.

2. **Stage 2: Propose version bump from commit history**
   - Inspect commits since the last release tag using `git log`.
   - Classify commits by type:
     - `feat!`, `fix!`, or `BREAKING CHANGE`: Major bump (X.0.0).
     - `feat`: Minor bump (0.X.0).
     - `fix`, `docs`, `perf`, `refactor`: Patch bump (0.0.X).
   - Gate: Proposed version bump matches commit rationale.

3. **Stage 3: Update changelog**
   - Update `CHANGELOG.md` with new version section and date.
   - Categorize entries into Added, Changed, Fixed, and Removed.
   - Keep entries concise and factual.
   - Gate: Changelog updated accurately reflecting git history.

4. **Stage 4: Verification check**
   - Run `commands.check` to confirm documentation changes pass checks.
   - Gate: Project check exits 0.

5. **Stage 5: Propose release command**
   - Present release summary with proposed version.
   - Output the exact `git tag` command for the user to execute.
   - Gate: Tag command presented to user. Never tag, push, or publish.

## What to read

- `git status` (must be clean).
- `git log` since the last tag.
- Project manifest (`package.json`, `Cargo.toml`, or `pyproject.toml`).
- `CHANGELOG.md`.
- `.agents/project-profile.yaml`: Commands and git configuration.

## What to produce

- Proposed version bump with commit analysis.
- Updated `CHANGELOG.md` with changes grouped by category.
- Verification check output.
- Exact `git tag` command for maintainer execution.

## Stop conditions

- Working tree has uncommitted changes: stop and ask user to commit or stash.
- Project check fails: stop immediately. Never prepare a release for failing code.
- Never run `git tag`, `git push`, or `npm publish`. Always leave tagging and publishing to the user.
