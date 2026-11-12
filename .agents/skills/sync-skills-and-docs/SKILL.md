---
name: sync-skills-and-docs
description: Use when a change adds, moves or removes a screen, component, file, folder, token, route, command, storage key, commit scope, capability or rule in a project that has a .agents/project-profile.yaml. Updates the profile first, re-renders AGENTS.md and the convention skills from it, refreshes the README and repo map, and runs a drift checker. Use it at the end of any structural change, and whenever docs, skills or the profile might be out of date.
compatibility: Needs file read, file edit, shell, git, Python 3, and PyYAML.
---

# Keep docs and skills in sync

Stage 6 of the pipeline. Rules live once, in the profile. AGENTS.md and the convention skills are generated from it. So the order is always: profile first, then generated files, then prose docs. If you edit a generated file by hand, the next re-render erases the edit.

## Read first

`.agents/project-profile.yaml`, section `docs`. It names the README, the AGENTS file, the skills folder and the repo map.

## Map: what changed, what to update

| Change | Update in the profile | Also update |
|---|---|---|
| File or folder added, moved or removed | `structure.layers`, `structure.root_allowed` | README structure section, repo map |
| Token, primitive, icon or font rule | `design`, `rules` (areas `design`, `tokens`) | README token section |
| Breakpoint or layout rule | `responsive`, `rules` (area `responsive`) | |
| Storage key, schema or data rule | `data`, `rules` (area `data`) | README data section |
| Command or test rule | `commands`, `verification` | README commands |
| Naming rule | `naming`, `rules` (area `naming`) | |
| New commit scope or type | `git.scopes`, `git.types` | |
| New rule for agents | `rules` | |
| Capability or external reference | `capabilities`, `external_references` | |
| Reference added, removed or updated | `references.yaml`, `references.lock.json` through `refs.py` | Re-render AGENTS.md |
| Blueprint facts, models or tokens | `blueprints` | Run blueprint extract, check_sync |
| Post-build audit format | `verification` | |

## Steps

1. **List what changed.** Use `git diff --stat` or the commit list for the task.
2. **Edit the profile.** Make the smallest change that makes it true. One id per rule, written once. Remove stale rules. Do not leave contradictions.
3. **Validate.** Run `python3 .agents/skills/project-bootstrap/scripts/validate_profile.py --profile .agents/project-profile.yaml --root .`.
4. **Re-render.** Run `python3 .agents/skills/project-bootstrap/scripts/render.py --profile .agents/project-profile.yaml --root . --update`.
   - `--update` preserves custom blocks (`<!-- BEGIN CUSTOM: name -->`) byte for byte and regenerates surrounding templates.
   - If hand edits exist outside custom blocks, `--update` refuses the file, prints a unified diff, and leaves files unchanged. Run with `--salvage` (or `--force`) to regenerate and preserve hand edits into a `salvaged` custom block. Hand edits are never discarded unless `--discard-edits` and `--yes-discard` are passed together.
   - Unstamped files are never overwritten silently. Run with `--migrate-custom` to wrap unstamped files into a `legacy` custom block, or `--force --overwrite-unstamped` to overwrite.
   - If project-bootstrap is not installed, edit the generated files to match the profile by hand and say so.
   - Run `python3 .agents/skills/project-bootstrap/scripts/check_preservation.py --root . --base <base_ref> --head HEAD` to confirm that non-generated rules and table rows are preserved.
5. **Refresh the repo map.** Run `repo-search` in map mode.
6. **Update the README** sections named in the map above.
7. **Search for old names.** Search the docs, skills and README for names that no longer exist: moved files, removed components, removed tokens, old commands.
8. **Flag, do not delete.** If a skill no longer applies, add it to the section "Skills flagged for review" in the repo map. Never delete it silently.
9. **Run the drift checker and blueprint drift.**

```bash
python3 .agents/skills/sync-skills-and-docs/scripts/check_sync.py --profile .agents/project-profile.yaml --root .
python3 .agents/skills/project-blueprints/scripts/blueprint.py drift
```

If python3 is not found, use python or py -3.

Fix every error. Read every warning and decide.

10. **Run `commands.check`.** The docs change must not break the build.

## Checklist

- [ ] The README structure matches the layers in the profile.
- [ ] The commands in the profile match the project manifest.
- [ ] Every skill named in AGENTS.md exists in the skills folder.
- [ ] No doc names a file, token or command that no longer exists.
- [ ] Every commit scope in recent history is in `git.scopes`.
