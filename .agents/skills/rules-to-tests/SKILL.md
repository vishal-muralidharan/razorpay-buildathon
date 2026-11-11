---
name: rules-to-tests
description: Turn written project rules into automatic checks that fail the build when broken. Reads the rules in .agents/project-profile.yaml, finds the ones a script can verify (no raw color values, no emojis, no forbidden files, a clean repo root, required files), adds a machine check to each, copies a runner into the project and hooks it into the single check command. Use it after project-bootstrap or scaffold-app, when the user says "enforce this rule", "make a rule test", "stop agents from breaking X", "add a lint rule for our conventions", or when a rule keeps getting broken by hand.
compatibility: Needs file read, file edit, shell, Python 3, and PyYAML.
---

# Rules to tests

A rule that only lives in prose gets broken the first time an agent is in a hurry. A rule that fails the build does not. This skill moves every rule that a script can judge from prose to enforcement.

## Read first

1. `.agents/project-profile.yaml`: the `rules` list, `structure.root_allowed`, `commands` and `design.enforced_by`.
2. `references/check-patterns.md` for ready patterns and for what a script cannot judge.

## Steps

1. **Sort the rules.** Go through every rule in `.agents/project-profile.yaml`. Distinguish:
   - **Pack rules with checks:** rules with `pack: <id>@<version>` that have a `check` block (from `native-controls`, `web-hazards`, `mobile-web`, `a11y-basics`, `motion-basics`, or `testing-practices`). These run mechanically via `run_rule_checks.py`.
   - **Pack rules without checks:** rules with `pack: <id>@<version>` and `enforced_by: manual` (and verify checks from packs like `ui-states`, `shortcuts`, or `browser-checks`). These are manual verify checks, recorded under the test plan or browser checks. Never fake a check for them.
   - **Project rules:** for rules without a pack, inspect each rule with `enforced_by: manual`:
     - **Mechanical:** a pattern, a file, a folder rule, or a structure constraint (like `no_dual_homed_skills`) can decide it. Example: "No emojis anywhere." or "A reference lives in .agents/vendor or .agents/skills, never both."
     - **Judgment:** it needs a person. Example: "Keep copy to 1 or 2 words." Leave these manual. Do not fake a check for them.
2. **Write each check.** Add a `check` block to the mechanical rules. Use the check types in the profile schema: `forbid`, `require_file`, `forbid_file`, `root_only`, and `no_dual_homed_skills`. Start from `references/check-patterns.md`. The `no_dual_homed_skills` pattern checks that no reference skill is installed in both `.agents/vendor` and `.agents/skills`. It runs whenever rule checks execute in CI or pre-commit verification. Keep patterns narrow, so they do not flag valid code.
3. **Prove each check on both sides.**
   - Run the runner. The check must pass on the current code. If it fails on real violations, tell the user and either fix the code (through `feature-delivery`) or narrow the pattern.
   - Add 1 deliberate violation in a temporary file. Confirm the check fails. Remove the file. A check that has never failed has not been proven.
4. **Set enforcement.** For each rule with a working check, set `enforced_by: test`. Set `design.enforced_by` to the runner path when design rules use checks.
5. **Install or refresh the runner.** Copy `scripts/run_rule_checks.py` to `.agents/checks/run_rule_checks.py` in the project. If `.agents/checks/run_rule_checks.py` already exists with an older `RUNNER_VERSION`, show the diff and copy the newer runner only after the user says yes. The project then does not depend on this skill being installed.
6. **Hook it into `check` and CI.** Add the runner to the single check command, for example `python3 .agents/checks/run_rule_checks.py`, ahead of the build. If python3 is not found, use python or py -3. For JavaScript projects add a `rules` script and chain it in the `check` script. For other stacks, add it to the equivalent chain. Update `commands.check` in the profile if the command text changes. To enforce rule checks in GitHub Actions, copy `assets/rules-ci.yml` to `.github/workflows/agent-rules.yml`.
7. **Validate and render.** Run `validate_profile.py`, then re-render with `project-bootstrap` so the generated skills show `(enforced by test)`.
8. **Commit** with `atomic-commits`: 1 commit for the profile checks, 1 for the runner and the hook.
9. **Report.** List rules now enforced, rules left manual, and why.

## Rules for this skill

- A check never edits files. It only reports.
- Never weaken or delete a check to make a build pass. If a rule should change, change the rule in the profile through `sync-skills-and-docs`, with the user's yes.
- Do not claim a rule is enforced unless its check ran and passed in this session.
- Excluded paths must be listed explicitly in `exclude`. Do not hide violations behind broad globs.
- Cross-platform paths: Check runners and rule scripts must normalize file paths using POSIX slashes (such as `Path.as_posix()`) before matching against globs or regexes so checks behave identically across Linux, macOS and Windows.
