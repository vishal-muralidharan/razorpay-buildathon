---
name: scaffold-app
description: Create the first working skeleton of a new app from its project profile. Uses the framework's official generator, lays out the profile's folders, sets up lint, test, build and a single check command, adds design tokens if the profile wants them, and ends with a green check and a first commit. Use it right after project-bootstrap in new mode, or whenever the user says "scaffold", "set up the project", "create the app", "initialize the repo" or "start the codebase". Do not use it on a repo that already has working code.
compatibility: Needs file read, file edit, shell, git, Python 3, network access, and the toolchain for the chosen stack.
---

# Scaffold app

Turns a validated profile into a skeleton that builds, lints and tests green. It adds no product features. Features come later, through `feature-delivery`. Stopping at a green skeleton keeps the first commits small and makes every later failure the fault of new code.

## Read first

1. `.agents/project-profile.yaml`. It must exist, have `project.mode: new`, and pass `validate_profile.py` with no errors. If not, run `project-bootstrap`.
2. The product spec if `docs.spec` is set. Read milestone 1 so the skeleton fits it. Do not build milestone 1 here.
3. `references/stack-recipes.md` for the recipe that matches `stack.framework`.

## Steps

1. **Check the target folder.** If it holds files other than `.agents/`, `docs/`, `.git/` and the profile, ask before continuing. Never overwrite existing files without a yes. If a reference with category backend or deploy exists for this stack, read it before you choose the recipe. It never overrides the profile.
2. **Run the official generator.** Use the framework's own create tool. Do not hand write boilerplate that a generator provides. Look up the exact command in the framework's current docs, because flags change. Use non interactive flags. Generate into a temporary folder if the target is not empty, then copy files in.
3. **Install and get a baseline.** Run `commands.install`. Run the generated lint, test and build. All must pass before you change anything. If the generator's output fails, stop and report. Do not paper over it.
4. **Apply the profile layout.** Create every folder in `structure.layers`. Move generated files into the layers where they belong. Put a `.gitkeep` in a layer that is still empty.
5. **Wire the commands.** Make sure every non empty command in `commands` runs. For JavaScript projects run `python3 .agents/skills/scaffold-app/scripts/ensure_check_script.py --root . --profile .agents/project-profile.yaml` to add the single `check` script. If python3 is not found, use python or py -3. For other stacks, create the equivalent chain by hand.
6. **Design tokens.** If `design.enabled`, copy `assets/tokens.base.css` to `design.tokens_file`. Adjust it to the design rules in the profile. Import it once at the app entry. Tokens only. Build shared components later, when a feature first needs one.
7. **Test setup.** Make sure the test runner works with 1 small smoke test and any setup file the stack needs. Place tests as `structure.tests` says.
8. **Housekeeping.** Add a `.gitignore` for build output, dependencies and caches. Write a short `README.md` with the commands from the profile.
9. **Rule checks.** If any rule in the profile has a `check` block, or the user wants automatic rule enforcement, run `rules-to-tests`.
10. **Render the guidance files.** Run `python3 .agents/skills/project-bootstrap/scripts/render.py --profile .agents/project-profile.yaml --root .` so AGENTS.md and the convention skills match the final layout.
11. **Verify.** Run `commands.check`. It must pass with 0 errors and 0 warnings.
12. **Sync the profile.** If the generator forced a different layout than the profile describes, update the profile through `sync-skills-and-docs`. Do not leave the profile wrong.
13. **Commit** in small units with `atomic-commits`. Suggested units: generator output, layout and commands, tokens, test setup, docs. Use type `chore` for the skeleton. Do not push unless the profile allows it.
14. **Report and hand off.** List what exists, what was changed from the profile and why, and that the next step is `feature-delivery` for milestone 1.

## Rules

- No product features, no sample screens, no placeholder data. A skeleton only.
- It creates no components, by design. Components are created when a feature first needs one, through the Form controls workflow in build-ui.
- Add only dependencies the profile's stack needs. Each extra dependency needs a reason and the user's yes.
- Never write secrets or keys into files. Use environment files that are ignored by git, and tell the user which variables will be needed.
- If a generator or install step fails twice, stop and report the exact error.
