# Project profile schema (version 1)

File: `.agents/project-profile.yaml`. Copy `assets/project-profile.template.yaml` to start. Validate with `scripts/validate_profile.py`.

## Contents

1. Fields
2. Rules list
3. Capabilities and external references
4. Which stage reads which field

## 1. Fields

| Field | Type | Notes |
|---|---|---|
| `schema_version` | int | 1 or 2 (SUPPORTED_SCHEMA_VERSIONS = (1, 2)). |
| `project.name` | string | Required. |
| `project.summary` | string | Required. One sentence. |
| `project.mode` | `existing` or `new` | Required. |
| `project.platforms` | list | web, pwa, desktop, ios, android, cli, api. |
| `stack.*` | string | `language`, `framework`, `package_manager` are required. Use `none` for slots that do not apply. |
| `commands.*` | string | Exact shell commands. Empty means not available. `check` must run lint, test and build. Or set all 3 separately. `test_single` uses `{path}`. |
| `structure.layers` | list | At least 1. Each has `path` and `purpose`. |
| `structure.root_allowed` | list | Files and folders allowed in the repo root. |
| `structure.tests` | `colocated` or `tests-dir` | Required. |
| `naming` | list | Each has `item`, `style`, `example`. |
| `design.*` | mixed | If `enabled` is true, `tokens_file` is required. `enforced_by` names the test or lint rule. |
| `responsive.*` | mixed | If `enabled`, `min_width` must be below `max_width`. `breakpoints` entries have an integer `from` and a `layout` string. |
| `data.*` | mixed | `storage`, `schema_source`, `invariants`, `protected`. Protected items need user approval to change. |
| `git.*` | mixed | `push` is `never`, `ask` or `allowed`. `scopes` is a list of strings or `{name, purpose, paths}` objects. Empty means free scope. `workflow` sets opt-in branch workflow options. |
| `verification.*` | mixed | `zero_warnings`, `browser_checks`, `post_build_report`. |
| `docs.*` | paths | `skills_dir`, `agents_file`, `repo_map` are required. `spec` is optional and names the product spec file. |
| `blueprints.*` | mixed | Optional. `enabled`, `dir`, and `areas`. Do not store raw lists of keys or tokens in profile. |
| `rule_packs` | list of objects | Optional. Recorded installed rule packs as `[{id, version}]`. |
| `dropped_pack_rules` | list of strings | Optional. List of pack rule IDs permanently omitted by the user. |

### Commit scopes (`git.scopes`)

`git.scopes` defines the allowed commit scopes. Each entry can be:
1. A plain kebab-case string: `"ui"`
2. An object with `{name, purpose, paths}`:
   ```yaml
   - name: ui
     purpose: User interface components and styles
     paths:
       - src/components/**
       - src/styles/**
   ```

Mixed lists are allowed. `name` must be unique and kebab-case. `purpose` is optional and must be 100 characters or fewer. `paths` is an optional list of file globs used by `suggest_scope.py`.

### Branch workflow (`git.workflow`)

Opt-in configuration for feature and bug fix branch mode:
- `default_branch`: default branch name (e.g. `main` or `master`, detected from repo).
- `mode`: `off`, `ask`, or `always` (default `ask`).
- `branch_format`: branch name template, default `"<type>/<slug>"`. Type must be in `git.types`, slug must be kebab-case, 40 characters or fewer.
- `sync`: `merge` or `rebase` (default `merge`).
- `merge_method`: `squash`, `merge`, or `rebase` (default `squash`).
- `remote`: remote name, default `origin`.
- `cleanup`: `ask` or `keep` (default `ask`).
- `worktree`: boolean, default `false`.

## 2. Rules list

Each rule is written once, here. Never copy a rule into AGENTS.md or a skill by hand. Re-render instead.

```yaml
- id: ui-no-emoji          # unique, kebab-case, starts with a short area prefix
  area: design             # design, tokens, motion, responsive, structure, naming, data, security, verify, git, docs, process
  text: No emojis anywhere.
  enforced_by: test        # manual, test or lint
  pack: "native-controls@1" # optional: pack and version that supplied the rule
  enforced_by_ref:         # optional: file and snippet proving enforcement when check is omitted
    file: "tests/lint.test.js"
    contains: "[ui-no-emoji]"
  evidence:                # optional list of source paths backing this rule
    - src/components/Emoji.tsx
```

- One sentence. Imperative. Plain words.

### Optional machine checks

A rule can carry a `check` block. `rules-to-tests` runs it. A rule with a check should set `enforced_by: test`.

| `check.type` | Fields | Fails when |
|---|---|---|
| `forbid` | `pattern` (regex), `include` (globs), `exclude` (globs, optional) | the pattern appears in an included file |
| `require_file` | `path` | the file is missing |
| `forbid_file` | `include`, `exclude` | any file matches the globs |
| `root_only` | none (uses `structure.root_allowed`) | the repo root holds an entry that is not allowed |
| `no_dual_homed_skills` | none | a skill exists in both .agents/vendor and .agents/skills |

```yaml
- id: ui-no-raw-hex
  area: design
  text: No raw hex values outside the tokens file.
  enforced_by: test
  check:
    type: forbid
    pattern: '#[0-9a-fA-F]{3,8}\b'
    include: ["src/**/*.{js,jsx,css}"]
    exclude: ["src/index.css"]
    hint: "Use design token variables instead of raw hex values."
    examples:
      bad: ["color: #ffffff;"]
      good: ["color: var(--color-background);"]
  exceptions:
    - path: "src/legacy/badge.css"
      reason: "Legacy badge styles pending design token migration"
```

### Rule exceptions

A rule may carry an `exceptions` list with `{path, reason}` items. The `reason` is required and non-empty. The check runner merges exception paths into the check exclude list. The profile validator errors when an exception lacks a reason, and warns when an exception path matches no existing file.

### Check hints and examples

A check block can include:
- `hint`: short sentence naming the fix. The runner prints this on failure.
- `examples`: mapping with `bad` and `good` lists. Tested by `run_rule_checks.py --selftest`.

### Rule packs

Predefined rule collections can be adopted during bootstrap hazard sweep or applied with `packs.py`:
- `native-controls`: Prevent unthemed native browser form controls outside component folders.
- `web-hazards`: Prevent common web security and hygiene hazards.
- `ui-states`: Require loading skeletons, empty states, and error alerts.
- `mobile-web`: Mobile web usability for input font sizing, tap targets, viewport insets, and pinch zoom.
- `shortcuts`: Keyboard shortcut conventions across platforms.
- `a11y-basics`: Accessibility fundamentals for semantic HTML, focus visibility, contrast, and image alt attributes.
- `motion-basics`: Motion and transition best practices and reduced motion support.
- `testing-practices`: Testing practices avoiding style assertions and brittle queries.
- `browser-checks`: Quality verification checks for console errors, contrast, listener cleanup, and viewport fit.

Profile fields for rule packs:
- `rule_packs`: list of installed packs as `[{id: <id>, version: <int>}]`.
- `rule.pack`: string in `<id>@<version>` format marking which pack and version supplied the rule.
- `dropped_pack_rules`: list of rule IDs permanently omitted by the user. `packs.py apply` never re-adds these rules.

- `enforced_by: test` or `lint` is a claim. Check that the test or rule exists before you set it.
- Where each area renders: `design` and `motion` go to `build-ui`. `tokens` goes to `maintain-design-system`. `responsive`, `structure`, `naming` and `data` go to the skill of the same topic. `process`, `security`, `verify`, `git` and `docs` go to the "Project rules" section of AGENTS.md.

## 3. Capabilities and external references

Capabilities are optional helpers. A disabled capability means the pipeline skips that stage.

```yaml
capabilities:
  deploy:
    enabled: true
    command: "npm run deploy"
    verify_url: "https://example.com"
    on_failure: self-heal      # or report
    max_attempts: 3            # self-heal stops after this many tries (1 to 10)
    reference: ""              # optional name from .agents/references.yaml
```

External references and third party skills live in `.agents/references.yaml`. Hashes and pinned commits live in `.agents/references.lock.json`. The profile keeps only capability slots that point to a reference by name. Manage references using `python3 .agents/skills/extend-pipeline/scripts/refs.py`.

Valid reference `used_by` stages: `audit`, `build`, `verify`, `deploy`, `report`. Valid `status`: `declared`, `installed`, `rejected`. Valid `mode`: `advisory`, `gate`. Valid `activation`: `pipeline-only`, `native`. Installed entries require `path`, `pinned_commit`, and `approved: true`.

## 4. Which stage reads which field

| Stage | Reads |
|---|---|
| Audit | `structure.layers`, `docs.repo_map`, `data.schema_source`, `rules` |
| Plan | `git.scopes`, `commands.check`, `data.protected` |
| Build | `design.*`, `responsive.*`, `naming`, `structure`, `rules` |
| Verify | `commands.*`, `verification.*`, `design.enforced_by`, `capabilities.browser_inspection` |
| Deploy | `capabilities.deploy`, `commands.deploy` |
| Commit | `git.*` |
| Docs | `docs.*`, every field that changed |
| Report | `verification.post_build_report` |
