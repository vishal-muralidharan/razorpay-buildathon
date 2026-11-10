# Bug Fix Workflow

Use this workflow when fixing a reported bug, defect, regression, or broken check in a project with a profile.

## When to use

- User reports a bug, defect, or unexpected behavior.
- An existing automated test fails.
- A regression was introduced during development.

## Stages with gates

1. **Stage 1: Reproduce and audit**
   - Reproduce the failure with a minimal test case or direct command.
   - Trace the exact execution path to find the root cause.
   - Gate: Root cause identified with evidence. Do not guess.

2. **Stage 2: Write failing regression test first**
   - Add an automated test that fails because of the bug.
   - Confirm the test fails with the expected failure mode.
   - Ensure the regression test is cross-platform safe: normalize path separators with `as_posix()` and avoid platform-specific shell constructs.
   - Gate: Test fails before any application code is changed.

3. **Stage 3: Make smallest fix**
   - Make the smallest code change that addresses the root cause.
   - Do not bundle opportunistic refactoring into the fix.
   - Gate: Fix directly addresses the root cause identified in Stage 1.

4. **Stage 4: Verify fix**
   - Re-run the regression test using `commands.test_single`.
   - Confirm the regression test passes.
   - Gate: Regression test exits with 0 errors.

5. **Stage 5: Full check**
   - Run `commands.check` across the entire project.
   - Confirm no collateral regressions were introduced.
   - Gate: Project check command exits 0 with 0 errors and 0 warnings.

6. **Stage 6: Report and commit**
   - Commit the fix and regression test together using `atomic-commits`.
   - Document root cause and prevention in the post-fix summary.
   - Gate: Atomic commit created with `fix(...)` prefix.

## What to read

- `.agents/project-profile.yaml`: Commands, rules, and data invariants.
- Issue description or bug report.
- Relevant source code and existing test files.
- Area convention skills (such as `build-ui` or `review-db-structure`) if UI or data layers are touched.

## What to produce

- 1 automated regression test reproducing the failure.
- Minimal source code patch fixing the root cause.
- 1 atomic commit with format `fix(<scope>): <message>`.
- Summary report stating root cause, fix mechanism, and prevention steps.

## Stop conditions

- Bug cannot be reproduced with available details: stop and ask user for reproduction steps.
- Fix requires changing protected data or breaking public API contracts: stop and ask user before proceeding.
- Fix fails after 2 attempts: revert changes with `git restore .` and re-evaluate root cause.
