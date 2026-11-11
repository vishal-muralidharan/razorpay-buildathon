# Check patterns

Ready patterns for the `check` block. Adjust `include` and `exclude` to the project. Prove every pattern on both sides before you trust it (see the skill steps).

YAML tip: write regexes in single quotes so backslashes stay literal.

## Contents

1. Patterns
2. Rule packs
3. Narrowing a noisy pattern
4. What a script cannot judge

## 1. Patterns

### No raw hex colors outside the tokens file

```yaml
check:
  type: forbid
  pattern: '(?<![\w&/])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b'
  include: ["src/**/*.{js,jsx,ts,tsx,css,html}"]
  exclude: ["src/index.css"]
```

### No rgb() or hsl() color functions

```yaml
check:
  type: forbid
  pattern: '\b(?:rgb|rgba|hsl|hsla)\('
  include: ["src/**/*.{js,jsx,ts,tsx,css}"]
  exclude: ["src/index.css"]
```

### No emojis

```yaml
check:
  type: forbid
  pattern: '[\U0001F300-\U0001FAFF\u2600-\u27BF]'
  include: ["src/**/*.{js,jsx,ts,tsx,css,html,md}", "README.md"]
```

### No palette color classes (Tailwind)

```yaml
check:
  type: forbid
  pattern: '\b(?:bg|text|border|ring|fill|stroke|from|to|via)-(?:red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|slate|gray|zinc|neutral|stone)-\d{2,3}\b'
  include: ["src/**/*.{js,jsx,ts,tsx,html}"]
```

### Native controls only inside the shared primitives

```yaml
check:
  type: forbid
  pattern: '<select\b'
  include: ["src/**/*.{jsx,tsx}"]
  exclude: ["src/components/ui/**"]
```

### No console logging in shipped code

```yaml
check:
  type: forbid
  pattern: '\bconsole\.(?:log|debug)\('
  include: ["src/**/*.{js,jsx,ts,tsx}"]
  exclude: ["**/*.test.*", "src/test/**"]
```

### Storage only through the storage layer

```yaml
check:
  type: forbid
  pattern: '\b(?:localStorage|sessionStorage|indexedDB)\b'
  include: ["src/**/*.{js,jsx,ts,tsx}"]
  exclude: ["src/lib/storage.js", "src/test/**", "**/*.test.*"]
```

### No `any` in TypeScript

```yaml
check:
  type: forbid
  pattern: ':\s*any\b'
  include: ["src/**/*.{ts,tsx}"]
```

### A clean repo root

```yaml
check:
  type: root_only
```

Needs `structure.root_allowed` in the profile.

### No dual-homed skills

```yaml
check:
  type: no_dual_homed_skills
```

What it checks: Fails when any skill or reference exists in both `.agents/vendor` and `.agents/skills`, or when frontmatter names collide.
When it runs: Runs during automated rule checks in CI, pre-commit checks, or when running `run_rule_checks.py`. Takes no parameters.

### A required file exists

```yaml
check:
  type: require_file
  path: README.md
```

### A removed folder stays removed

```yaml
check:
  type: forbid_file
  include: ["src/pages/**"]
```

## 2. Rule packs

Ready packs combining multiple rules for common stacks. Installed via `packs.py apply <id>`.

### Native controls pack (`native-controls`)

Prevent native browser form controls outside component folders.
Requires the project to use themed primitives for pickers, selects, and dialogs.

#### 1. No native pickers (`ui-no-native-pickers`)

```yaml
- id: ui-no-native-pickers
  area: design
  text: Never use native browser date, time, month, week, datetime-local, or color inputs instead of the project's themed picker primitives.
  enforced_by: test
  check:
    type: forbid
    pattern: '(?<![\w-])type\s*=\s*(?:\{\s*)?["\x27\x60](?:date|time|color|datetime-local|month|week)["\x27\x60]'
    include: ["src/**/*.{js,jsx,ts,tsx,vue,svelte,html}"]
    exclude: ["{{component_dirs}}/**"]
    hint: Use the project's themed picker primitive instead of native date/time/color inputs.
    examples:
      bad:
        - '<input type="date">'
        - "<input type={'time'}>"
      good:
        - '<DatePicker>'
        - '<input type="text">'
```

#### 2. No native selects (`ui-no-native-selects`)

```yaml
- id: ui-no-native-selects
  area: design
  text: Never use native browser select elements instead of the project's themed Select primitive.
  enforced_by: test
  check:
    type: forbid
    pattern: '<select\b'
    include: ["src/**/*.{js,jsx,ts,tsx,vue,svelte,html}"]
    exclude: ["{{component_dirs}}/**"]
    hint: Use the themed Select primitive instead of a native select element.
    examples:
      bad:
        - '<select>'
      good:
        - '<Select>'
```

Note: A native `<select>` inside `PrimitiveSelect.tsx` is allowed because `exclude` covers `{{component_dirs}}/**`.

#### 3. No browser dialogs (`ui-no-browser-dialogs`)

```yaml
- id: ui-no-browser-dialogs
  area: design
  text: Never use window alert, confirm, or prompt instead of the project's dialog and toast primitives.
  enforced_by: test
  check:
    type: forbid
    pattern: '(?<![\w.$])(?:window\.)?(?:alert|confirm|prompt)\s*\('
    include: ["src/**/*.{js,jsx,ts,tsx,vue,svelte,html}"]
    exclude: ["**/*.test.*", "**/*.spec.*", "src/test/**"]
    hint: Use a themed modal dialog or toast notification instead of window alert, confirm, or prompt.
    examples:
      bad:
        - 'alert("x")'
        - "confirm('y')"
        - 'prompt(`z`)'
      good:
        - '<ConfirmDialog />'
        - 'customDialog.confirm("Save changes?")'
```

#### Test corpus summary

The 6 bad examples and 5 good examples for native controls verification:
- Bad (6): `<input type="date">`, `<input type={'time'}>`, `<select>`, `alert("x")`, `confirm('y')`, `prompt(`z`)`.
- Good (5): `<DatePicker>`, `<Select>`, native `<select>` inside `PrimitiveSelect.tsx` (wrapped in component directory), custom dialog primitive, and non-picker input like `type="text"`.

### Web hazards pack (`web-hazards`)

Common security and hygiene hazards to prevent in any web codebase. Each rule has a check, examples and a hint.

#### 1. No console in shipped code (`web-no-console`)

```yaml
- id: web-no-console
  area: verify
  text: Never ship console.log or console.debug in production code. Use a dedicated logger or test file.
  enforced_by: test
  check:
    type: forbid
    pattern: '(?<![\w.$])console\.(?:log|debug)\s*\('
    include: ["src/**/*.{js,jsx,ts,tsx,vue,svelte,html}"]
    exclude: ["**/*.test.*", "**/*.spec.*", "src/test/**"]
    hint: Remove console.log or console.debug, or use a dedicated logging primitive.
    examples:
      bad:
        - 'console.log("user data:", user);'
        - 'console.debug("fetching auth state");'
      good:
        - 'console.error("failed to initialize:", err);'
        - 'console.warn("deprecated property accessed");'
        - 'logger.log("audit event");'
```

#### 2. Target blank rel protection (`web-target-blank-rel`)

Flags `target="_blank"` without `rel` containing `noopener` or `noreferrer` on the same tag line.
Note on multi-line limit: Multi-line HTML tags where `rel` is on a separate line are not matched by this single-line regex.

```yaml
- id: web-target-blank-rel
  area: security
  text: Links with target="_blank" must include rel="noopener" or rel="noreferrer" on the same line to avoid tabnabbing.
  enforced_by: test
  check:
    type: forbid
    pattern: '^(?!.*rel=["\x27][^"\x27]*(?:noopener|noreferrer)).*target=["\x27]_blank["\x27]'
    include: ["src/**/*.{js,jsx,ts,tsx,vue,svelte,html}"]
    hint: Add rel="noopener" or rel="noopener noreferrer" to links with target="_blank".
    examples:
      bad:
        - '<a href="https://example.com" target="_blank">External Link</a>'
        - "<a target='_blank' href=\"https://example.com\">Documentation</a>"
      good:
        - '<a href="https://example.com" target="_blank" rel="noopener">External Link</a>'
        - '<a href="https://example.com" rel="noopener noreferrer" target="_blank">Documentation</a>'
        - '<a href="/dashboard" target="_self">Dashboard</a>'
```

#### 3. No raw eval (`web-no-raw-eval`)

```yaml
- id: web-no-raw-eval
  area: security
  text: Never use eval() or equivalent dynamic execution without a listed exception.
  enforced_by: test
  check:
    type: forbid
    pattern: '(?<![\w$])(?:window\.)?eval\s*\('
    include: ["src/**/*.{js,jsx,ts,tsx,vue,svelte,html}"]
    hint: Do not use eval(). Parse structured data with JSON.parse or safe dispatch.
    examples:
      bad:
        - 'eval(untrustedInput);'
        - 'window.eval("calculate()");'
      good:
        - 'JSON.parse(untrustedInput);'
        - 'calculateValue(payload);'
```

#### 4. No raw innerHTML or dangerouslySetInnerHTML (`web-no-inner-html`)

```yaml
- id: web-no-inner-html
  area: security
  text: Never assign to innerHTML or use dangerouslySetInnerHTML without a listed exception.
  enforced_by: test
  check:
    type: forbid
    pattern: '(?<![\w$])(?:innerHTML\s*=|dangerouslySetInnerHTML\b)'
    include: ["src/**/*.{js,jsx,ts,tsx,vue,svelte,html}"]
    hint: Do not inject raw HTML. Use textContent or sanitized framework primitives.
    examples:
      bad:
        - 'container.innerHTML = renderedSnippet;'
        - '<div dangerouslySetInnerHTML={{ __html: rawHtml }} />'
      good:
        - 'container.textContent = textValue;'
        - '<div className="content">{textValue}</div>'
```

#### 5. No committed .env file (`web-no-committed-env`)

```yaml
- id: web-no-committed-env
  area: security
  text: Never commit .env files containing local configurations or secrets.
  enforced_by: test
  check:
    type: forbid_file
    include: [".env", ".env.local", ".env.*.local", "**/.env", "**/.env.local"]
    exclude: [".env.example", ".env.template", "**/.env.example", "**/.env.template"]
    hint: Never commit .env files with secrets or local config. Add .env to .gitignore and commit .env.example.
    examples:
      bad:
        - '.env'
        - 'apps/web/.env.local'
      good:
        - '.env.example'
        - 'apps/web/.env.template'
```

## 3. Narrowing a noisy pattern

- **Too many hits on valid code:** tighten with lookbehind, such as `(?<![\w&/])`, or require a surrounding character.
- **A known safe file:** add it to `exclude`. List it by path. Never exclude a whole source folder.
- **Generated files:** exclude the generated folder explicitly.
- **Tests that must contain the bad value:** exclude `**/*.test.*`.

## 4. What a script cannot judge

Leave these as `manual`, or cover them with browser checks if that capability is on:

- Copy quality, tone and length.
- Visual layout, spacing and polish.
- Color contrast (needs rendering).
- Whether a component is used correctly.
- Performance and memory behavior.
- Whether a name is meaningful.
