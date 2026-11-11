---
name: repo-search
description: Use to find out whether a feature, component, hook, helper, data field, style token or any symbol already exists in the repo, and where it is declared and used. Read-only discovery that reports findings without editing code. Also refreshes the repo map on request. Use it before creating any new file or function, when the user asks "is there already a...", "where is...", "find usages of...", or "refresh the repo map", and whenever audit-and-planning needs a search phase.
compatibility: Needs file read, file edit, and shell access.
---

# Repo search

Two modes. Search mode is the default. Map mode runs only when asked.

## Read first

1. `.agents/project-profile.yaml`. If it is missing, run `project-bootstrap`.
2. The repo map at `docs.repo_map`. Use its layer table to narrow the search before you scan the whole tree.

## Search mode (read only)

Do not edit, add or delete any file in this mode. Report findings in chat. Only the user can ask for a written report file.

1. **Find names and variants.** Search the exact name, PascalCase, camelCase, kebab-case and snake_case forms, plus related CSS classes or data field names.
2. **Separate declarations from usages.** Find the file that defines the symbol. Then list the files that import or call it.
3. **Check the layer.** Compare the declaration's folder with `structure.layers`. Say whether it sits in the right layer.
4. **Check state and storage.** Say whether it reads or writes shared state, storage, or the schema in `data.schema_source`.
5. **Check conformance.** If `design.enabled`, check that it uses tokens from `design.tokens_file`. If `responsive.enabled`, check touch target size and width handling.
6. **Report.**

Where to look, in order: the layers in the repo map, then the tests, then the docs and agent files (`README.md`, AGENTS.md, the skills folder).

### Output format

Use paths relative to the repo root. Never use absolute paths or machine specific links.

```
Target: <symbol or feature searched>
Found: yes | no | partial
Declaration: <path:line>
Usage sites: <paths>
Layer: <layer from the profile> (correct | misplaced)
State and storage: <what it touches, or none>
Conformance: <design and layout findings, or not applicable>
Verdict: reuse | extend | create new, with the reason
```

If nothing is found, say so and list the exact queries you tried.

## Map mode (writes one file)

Run only when the user asks for a refresh, or when `sync-skills-and-docs` calls for it. In this mode you may write only the file at `docs.repo_map`. Change nothing else.

1. List the folders that hold files, to a depth of 3, under each source root named in `structure.layers`.
2. For each layer in the profile, record up to 5 key files.
3. Add a row for any folder that has files but no layer. Mark its purpose as `TODO` and tell the user to resolve it in the profile.
4. Set the line "Last full scan" to today's date.
5. Keep the section "Skills flagged for review" if it exists.

The map is a cache. It saves every later task from rescanning the repo. A stale map is worse than none, so refresh it after any structural change.
