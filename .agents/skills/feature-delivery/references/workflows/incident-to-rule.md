# Incident to Rule Workflow

Use this workflow when a task fixes a violation of an unwritten convention, the user says "this should never happen again", or a review finds a recurring pattern that needs enforcement.

## When to use

- A task fixes a violation of an unwritten project convention.
- The user says "this should never happen again" or requests guardrails.
- A code review or audit detects a pattern that should be codified.
- Post-Build Audit identifies that a change worked around a missing rule.

## Stages with gates

1. **Stage 1: Propose rule definition**
   - Propose a rule: `id`, `area`, and `text`.
   - The rule id is kebab-case and starts with a short area prefix (such as `sec-no-eval` or `ui-no-raw-hex`).
   - The text is 1 imperative sentence stating the requirement in plain words.
   - Gate: User approves the proposed rule text, area, and id.

2. **Stage 2: Propose check or manual enforcement**
   - If a script can judge the condition (by pattern, forbidden file, or required file), propose a `check` block.
   - Include a `hint` naming the fix in 1 short sentence.
   - Include `examples` with `bad` and `good` sample strings or paths.
   - If the rule requires human judgment, set `enforced_by: manual`.
   - Gate: Check definition or manual determination approved.

3. **Stage 3: Selftest and repository proof**
   - Run `--selftest` with `python3 .agents/checks/run_rule_checks.py --selftest`.
   - Every bad example must match and every good example must not match.
   - Run the runner on the current repository: `python3 .agents/checks/run_rule_checks.py`.
   - If the pattern already exists elsewhere in the repository:
     - List each violation with file:line evidence.
     - Offer 2 choices: fix the violations now, or record them as exceptions with reasons (`exceptions: [{path, reason}]`).
   - Run a deliberate violation in a temporary file to confirm the check fails, then delete the temporary file.
   - Gate: Selftest passes with 0 failures and all existing occurrences are either fixed or recorded as exceptions.

4. **Stage 4: Profile update and re-render**
   - Add the approved rule and its check or exceptions to `.agents/project-profile.yaml`.
   - Set `enforced_by: test` for rules with checks, or `enforced_by: manual` for manual rules.
   - Validate the profile using `python3 .agents/skills/project-bootstrap/scripts/validate_profile.py --profile .agents/project-profile.yaml`.
   - Re-render documentation with `python3 .agents/skills/project-bootstrap/scripts/render.py --profile .agents/project-profile.yaml`.
   - Gate: Profile passes validation with 0 errors.

5. **Stage 5: Separate commit**
   - Never combine rule additions into the application fix commit.
   - Commit the rule changes separately from the fix using `atomic-commits`.
   - Use commit format `feat(rules): add <rule-id> check` or `docs(rules): document <rule-id> rule`.
   - Gate: Rule changes committed independently from application code changes.

## What to read

- `.agents/project-profile.yaml`: Existing rules and area conventions.
- `references/check-patterns.md`: Ready patterns, rule packs, and narrowing guidelines.
- The incident description, bug report, or code review comment.

## What to produce

- 1 new rule in `.agents/project-profile.yaml` with unique id, area, and text.
- 1 check block with hint and examples, or an explicit manual designation.
- Documented exceptions for any pre-existing occurrences that cannot be fixed immediately.
- 1 atomic commit separate from the bug fix.

## Stop conditions

- Pattern cannot be written without false positives across valid code: stop and ask user whether to narrow the pattern or keep the rule manual.
- Existing violations are extensive and cannot be fixed or exempted safely: stop and report findings before modifying the profile.

