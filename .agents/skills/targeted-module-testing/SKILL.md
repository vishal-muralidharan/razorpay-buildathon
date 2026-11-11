---
name: targeted-module-testing
description: Use after any change in a project that has a .agents/project-profile.yaml. Runs the verify, deploy and report stages. Runs lint, test and build commands, checks rule-enforcing tests, evaluates goal acceptance invariants, runs browser checks and a deploy loop only if enabled, and ends every task with a Post-Build Audit. Use it before you say a task is done, after every build, and whenever the user asks to verify, test, check, ship or deploy.
compatibility: Needs file read, shell, and network access if deploy checks are enabled.
---

# Verification, deploy and report

Stages 5, 7 and the optional deploy stage of the pipeline. A change is not done until checks pass, goal acceptance invariants are verified, and the report is written.

## Read first

`.agents/project-profile.yaml`: sections `commands`, `verification` and `capabilities`. Use the commands exactly as written there. Do not substitute your own.

## 1. Run the checks

| Check | Source | Pass when |
|---|---|---|
| Complete check | `commands.check` | exits 0 |
| Lint | `commands.lint` | 0 errors, and 0 warnings if `verification.zero_warnings` |
| Tests | `commands.test` | all pass |
| One test file | `commands.test_single` with `{path}` | passes |
| Build | `commands.build` | completes |

If `commands.check` is empty, run lint, test and build in that order. Empty commands are skipped. Say which ones you skipped.

When blueprints exist (`.agents/blueprints/`), run `python3 .agents/skills/project-blueprints/scripts/blueprint.py verify` after the checks.

Fix every failure at its cause. Do not edit a test or loosen a rule just to get a pass.

## 2. Tests

- Add a test for each new behavior. Update tests when visible copy changes.
- Assert on roles, labels and test ids. Do not assert on class names or colors.
- If `design.enforced_by` is set, that test or lint rule enforces the design rules. It must pass. Do not edit it to make a change pass unless the user agrees the rule should change. If the rule should change, change the profile through `sync-skills-and-docs`.
- Know what your test environment fakes (timers, layout, device APIs). Note any behavior that only a real browser can confirm.
- Cross-platform path assertions: When tests check CLI console output, file paths, or diffs, normalize path separators (`/` vs `\`) or use POSIX formatting (`Path.as_posix()`). Never assert hardcoded Unix slashes against raw host OS paths.
- Windows execution: When spawning child processes or npm commands in tests on Windows, pass `shell=(sys.platform == "win32")` for batch scripts (`npm.cmd`), and avoid shell wildcard expansion in npm test script targets.

## 2b. Goal Acceptance Verification

Automated tests exiting with code 0 does not prove that the user's objective was met.

1. Read `.agents/work/CURRENT_GOAL.md`. Confirm that `# Current Goal:` and the acceptance invariants reflect the active task being verified.
2. Evaluate each acceptance invariant listed under `Acceptance Invariants`:
   - Inspect data flow, API contract, or rendered component behavior against the expected invariant.
   - Confirm edge cases (zero states, invalid inputs, error handling) behave as intended.
3. Record invariant status:
   - Mark `[x]` for proven invariants.
   - If an invariant fails, record the observed deviation in `CURRENT_GOAL.md`.
   - This signal feeds directly into Stage 5a (Goal Loop) in `feature-delivery`.

## 3. Browser checks (optional)

Run only if `capabilities.browser_inspection.enabled` is true. Use the linked reference, if any, to run each sentence in `verification.browser_checks` against a build or preview.

If the capability is off, do not skip silently. List the checks under "Not run" in the report so the user can do them by hand.

## 3b. Reference checks

Run `python3 .agents/skills/extend-pipeline/scripts/refs.py due --stage verify --paths <changed files>`. Apply each listed reference to the change. Run a bundled script only if the listing says allow_scripts is true. Otherwise list it under 'Not run'. If a reference has mode gate and reports a blocking finding, stop and ask the user. Report findings under 'Third party review' in the Post-Build Audit, with the reference name.

## 4. Deploy (optional)

Run only if `capabilities.deploy.enabled` is true, and only after step 1 passes. Never deploy a failing build.

1. Run `capabilities.deploy.command` (or `commands.deploy`).
2. Check success: the command exits 0, and `verify_url` returns HTTP 200 when it is set. For example `curl -s -o /dev/null -w "%{http_code}" <verify_url>`.
3. On failure, if `on_failure` is `report`: stop. Show the failing output and the likely cause.
4. On failure, if `on_failure` is `self-heal`: read the failing output. If a linked reference documents a log command, use it. Diagnose the root cause. Fix it in code or project config with your editing tools. Re-run `commands.check`. Deploy again. Stop after `max_attempts` tries (default 3) and report what you tried.

Never change secrets, environment variables, hosting settings or billing during a self-heal loop. Ask the user instead.

## 5. Post-Build Audit

End every task with this section when `verification.post_build_report` is true. Fill it from what you actually observed. Do not pad it.

When all invariants pass, update `.agents/work/CURRENT_GOAL.md`: set `Status: completed`. If part of a series of tasks, mark the current task completed in `Series Queue` and prepare `CURRENT_GOAL.md` to transition to the next task in `feature-delivery`.

```markdown
### Post-Build Audit: Open Questions & Known Issues
- **Goal Invariants:** <all passed, or which invariants failed with evidence>
- **Checks:** <what ran and the result. Not run: <what was skipped and why>>
- **Try it:**
  1. <manual step 1 to verify behavior>
  2. <manual step 2 to verify behavior>
  3. <manual step 3 to verify behavior>
- **Known Issues:** <edge cases, quirks and limits you found>
- **Open Questions:** <decisions that need the user>
- **Rule Gaps:** Did this change work around a missing rule? <none, or missing convention to codify with incident-to-rule>
```

Always include 3 to 5 clear manual steps under "Try it" for each changed behavior so the user can test the change.

Look for known issues in these places, depending on the profile:

- Always: behavior that tests cannot prove, and edge cases of the new code.
- `responsive.enabled`: width limits, virtual keyboard overlap, safe areas and zoom.
- `design.enabled`: legibility in every theme, focus visibility and icon clarity.
- `data.storage` is set: storage quota, offline retries, migrations and idempotent writes.
- Keyboard shortcuts were added: modifiers across operating systems, and capture while typing in inputs.
- Rule gaps: check whether this task worked around an unwritten convention. If yes, name the convention and suggest running `incident-to-rule`.

Open questions are choices the user should make: trade-offs, label or placement choices, and future schema changes.

## 6. Finish

Do not commit here. Hand off to `atomic-commits`.
