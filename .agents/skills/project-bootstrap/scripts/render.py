#!/usr/bin/env python3
"""Render AGENTS.md, convention skills and a repo map from the project profile.

Usage: python render.py --profile PATH [--root REPO_ROOT] [--update] [--force] [--overwrite-unstamped] [--dry-run]

Rules live once, in the profile. The files written here are generated views.
Existing files are never overwritten unless --update or --force is set.
Custom blocks (<!-- BEGIN CUSTOM: name --> ... <!-- END CUSTOM: name -->)
are preserved byte for byte across updates.
Needs PyYAML (pip install pyyaml).
"""
import argparse
import difflib
import hashlib
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

BANNER = "<!-- Generated from {profile} by project-bootstrap. Edit the profile, then re-render. -->"
PROCESS_SKILLS = ["audit-and-planning", "repo-search", "atomic-commits",
                  "targeted-module-testing", "sync-skills-and-docs", "feature-delivery"]
OPTIONAL_SKILLS = [("feature-delivery", "Run any task from start to finish"),
                   ("product-spec", "Turn an idea into a spec and milestones"),
                   ("scaffold-app", "Create the first working skeleton of a new app"),
                   ("rules-to-tests", "Turn written rules into automatic checks"),
                   ("legal-and-settings-pages", "Settings, privacy, terms, consent and account deletion")]

CONVENTION_SKILLS = {
    "build-ui",
    "maintain-design-system",
    "review-responsive-design",
    "review-directory-structure",
    "file-folder-naming",
    "review-db-structure",
}

STAMP_RE = re.compile(r"^<!-- build-forge:generated v1 body=([0-9a-f]{64}) -->\n?", re.MULTILINE)
CUSTOM_BLOCK_RE = re.compile(
    r"<!-- BEGIN CUSTOM: ([a-z0-9-]{1,40}) -->\n?(.*?)<!-- END CUSTOM: \1 -->\n?",
    re.DOTALL
)
CUSTOM_NAME_RE = re.compile(r"^[a-z0-9-]{1,40}$")
OLD_BANNER_RE = re.compile(
    r"<!--\s*Generated from .+? by project-bootstrap\.\s*Edit the profile, then re-render\.\s*-->",
    re.IGNORECASE,
)

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password|passwd)\b\s*[:=]\s*['\"]?([A-Za-z0-9+/=_-]{20,})['\"]?"),
]


def normalize_lf(text: str) -> str:
    """Normalize line endings to LF."""
    return text.replace("\r\n", "\n")


def write_text_lf(path: Path, content: str) -> None:
    """Write text file with strictly LF line endings across all operating systems."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(normalize_lf(content))


def strip_stamp(text: str) -> str:
    """Remove stamp line if present."""
    return STAMP_RE.sub("", text)


def strip_custom_blocks(text: str) -> str:
    """Remove all custom blocks."""
    return CUSTOM_BLOCK_RE.sub("", text)


def compute_body_hash(text: str) -> str:
    """Compute sha256 hash of body with custom blocks and stamp removed, LF normalized."""
    norm = normalize_lf(text)
    clean = strip_stamp(norm)
    clean = strip_custom_blocks(clean)
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()


def stamp_text(text: str, body_hash: str) -> str:
    """Add or replace the stamp line after frontmatter (or at file top)."""
    norm = normalize_lf(text)
    clean = strip_stamp(norm)
    stamp_line = f"<!-- build-forge:generated v1 body={body_hash} -->\n"
    fm_match = re.match(r"^(---\n.*?\n---\n)(.*)$", clean, re.DOTALL)
    if fm_match:
        return f"{fm_match.group(1)}{stamp_line}{fm_match.group(2)}"
    return f"{stamp_line}{clean}"


def extract_custom_blocks(text: str, source_label: str) -> dict:
    """Extract custom blocks from text. Return dict of {name: inner_content}."""
    norm = normalize_lf(text)

    open_matches = list(re.finditer(r"<!-- BEGIN CUSTOM: ([^\s>]+) -->", norm))
    close_matches = list(re.finditer(r"<!-- END CUSTOM: ([^\s>]+) -->", norm))

    open_names = [m.group(1) for m in open_matches]
    close_names = [m.group(1) for m in close_matches]

    for name in open_names:
        if not CUSTOM_NAME_RE.match(name):
            sys.exit(f"ERROR: Invalid custom block name '{name}' in {source_label}. Names must match [a-z0-9-]{{1,40}}.")

    seen = set()
    for name in open_names:
        if name in seen:
            sys.exit(f"ERROR: Duplicate custom block name '{name}' in {source_label}.")
        seen.add(name)

    if len(open_names) != len(close_names):
        sys.exit(f"ERROR: Mismatched custom block tags in {source_label} ({len(open_names)} BEGIN vs {len(close_names)} END).")

    blocks = {}
    for m in CUSTOM_BLOCK_RE.finditer(norm):
        name = m.group(1)
        inner = m.group(2)
        blocks[name] = inner

    if set(open_names) != set(blocks.keys()):
        sys.exit(f"ERROR: Malformed or unclosed custom block in {source_label}.")

    return blocks


AREA_MAP = {
    "build-ui": "ui",
    "maintain-design-system": "tokens",
    "review-db-structure": "data",
    "review-responsive-design": "layout",
}


def resolve_blueprint_area(source_label: str) -> str:
    """Resolve blueprint area from convention skill source label."""
    for skill_name, area in AREA_MAP.items():
        if skill_name in source_label:
            return area
    return "data"


def scan_secrets(text: str, label: str) -> None:
    """Scan text for potential secrets and exit on match."""
    for pat in SECRET_PATTERNS:
        if pat.search(text):
            sys.exit(
                f"ERROR: Secret pattern detected in salvaged or migrated content for {label}. "
                "Refusing to proceed."
            )


def has_large_table_or_fenced_block(text: str, max_lines: int = 20) -> bool:
    """Check if markdown text contains tables or fenced blocks longer than max_lines."""
    lines = text.splitlines()
    in_fence = False
    fence_count = 0
    table_count = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_fence:
                if fence_count > max_lines:
                    return True
                in_fence = False
                fence_count = 0
            else:
                in_fence = True
                fence_count = 0
        elif in_fence:
            fence_count += 1
        elif stripped.startswith("|"):
            table_count += 1
            if table_count > max_lines:
                return True
        else:
            table_count = 0
    return False


def log_render_action(root: Path, rel_path: str, action: str, line_count: int) -> None:
    """Deterministically append salvage or migration entry to .agents/render-log.md."""
    log_file = root / ".agents" / "render-log.md"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    header = "# Render Log\n\nLog of salvaged edits and migrated custom blocks.\n\n"
    entry = f"- path: {rel_path} | action: {action} | lines: {line_count}\n"
    if log_file.is_file():
        existing = log_file.read_text(encoding="utf-8")
        if not existing.startswith("# Render Log"):
            existing = header + existing
        write_text_lf(log_file, existing.rstrip() + "\n" + entry)
    else:
        write_text_lf(log_file, header + entry)


def check_git_dirty(root: Path, targets: list, allow_dirty: bool) -> None:
    """Refuse if git reports uncommitted changes in target files unless allow_dirty is set."""
    if allow_dirty:
        return
    if not targets:
        return
    import subprocess
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--"] + [str(t) for t in targets],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print("NOTE  Git not available or not a git repository. Skipping dirty tree check.")
            return
        output = proc.stdout.strip()
        if not output:
            return
        dirty = []
        for line in output.splitlines():
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                dirty.append(parts[1].strip('"'))
            elif len(parts) == 1:
                dirty.append(parts[0])
        if dirty:
            dirty_str = ", ".join(dirty)
            sys.exit(
                f"ERROR: Target file(s) have uncommitted changes: {dirty_str}. "
                "Commit or stash changes before rendering, or pass --allow-dirty to overwrite."
            )
    except FileNotFoundError:
        print("NOTE  Git binary not found. Skipping dirty tree check.")
        return


def compute_salvaged_lines(clean_tmpl: str, clean_disk: str) -> list:
    """Find old body lines present in clean_disk that are absent from clean_tmpl."""
    diff = list(difflib.ndiff(clean_tmpl.splitlines(), clean_disk.splitlines()))
    return [l[2:] for l in diff if l.startswith("+ ")]


def route_overflow(root: Path, dest: Path, block_name: str, block_content: str, rel_label: str) -> None:
    """Route over-limit custom block through blueprint adopt or to .agents/notes/<skill>.md."""
    import subprocess
    skill_name = dest.parent.name if "skills" in dest.parts else dest.stem
    lines_count = len(block_content.splitlines())

    if skill_name in AREA_MAP:
        area = AREA_MAP[skill_name]
        bp_script = root / ".agents" / "skills" / "project-blueprints" / "scripts" / "blueprint.py"
        if not bp_script.is_file():
            bp_script = root / "skills" / "project-blueprints" / "scripts" / "blueprint.py"
        if not bp_script.is_file():
            bp_script = Path(__file__).resolve().parents[2] / "project-blueprints" / "scripts" / "blueprint.py"

        if bp_script.is_file():
            cmd = [
                sys.executable, "-B", str(bp_script),
                "adopt",
                "--from", str(dest),
                "--block", block_name,
                "--area", area,
                "--root", str(root),
            ]
            res = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
            if res.returncode != 0:
                sys.exit(f"ERROR: blueprint adopt failed for {rel_label} block '{block_name}':\n{res.stderr or res.stdout}")
            log_render_action(root, rel_label, f"adopt ({block_name} -> {area})", lines_count)
            print(f"ROUTED  Custom block '{block_name}' from {rel_label} into blueprint '{area}.md'")
            return

    # Route to notes if not in AREA_MAP or blueprint script unavailable
    notes_dir = root / ".agents" / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    notes_file = notes_dir / f"{skill_name}.md"

    header = f"# Notes for {skill_name}\n\n"
    block_entry = f"<!-- BEGIN CUSTOM: {block_name} -->\n{block_content.rstrip()}\n<!-- END CUSTOM: {block_name} -->\n"

    if notes_file.is_file():
        existing = notes_file.read_text(encoding="utf-8")
        if not existing.startswith(f"# Notes for {skill_name}"):
            existing = header + existing
        write_text_lf(notes_file, existing.rstrip() + "\n\n" + block_entry)
    else:
        write_text_lf(notes_file, header + block_entry)

    # In dest, replace the block content with pointer
    if dest.is_file():
        txt = dest.read_text(encoding="utf-8")
        pat = re.compile(
            rf"<!--\s*BEGIN CUSTOM:\s*{re.escape(block_name)}\s*-->\n?(.*?)<!--\s*END CUSTOM:\s*{re.escape(block_name)}\s*-->\n?",
            re.DOTALL
        )
        replacement = f"<!-- BEGIN CUSTOM: {block_name} -->\nMoved to .agents/notes/{skill_name}.md\n<!-- END CUSTOM: {block_name} -->\n"
        write_text_lf(dest, pat.sub(replacement, txt, count=1))

    log_render_action(root, rel_label, f"notes ({block_name} -> .agents/notes/{skill_name}.md)", lines_count)
    print(f"ROUTED  Custom block '{block_name}' from {rel_label} to .agents/notes/{skill_name}.md")


def validate_custom_blocks(blocks: dict, source_label: str, allow_overflow: bool = False) -> list:
    """Validate block line counts and secret patterns. Return list of warning strings."""
    warnings = []
    total_lines = 0

    area = resolve_blueprint_area(source_label)

    for name, content in blocks.items():
        lines = content.splitlines()
        count = len(lines)
        total_lines += count

        for pat in SECRET_PATTERNS:
            if pat.search(content):
                sys.exit(
                    f"ERROR: Secret pattern detected in custom block '{name}' in {source_label}. "
                    "Remove secrets from custom blocks."
                )

        if count > 160:
            adopt_cmd = f"python3 .agents/skills/project-blueprints/scripts/blueprint.py adopt --from {source_label} --block {name} --area {area}"
            if not allow_overflow:
                sys.exit(
                    f"ERROR: Custom block '{name}' in {source_label} has {count} lines (> 160). "
                    f"Facts belong in blueprints (.agents/blueprints/) or the profile (.agents/project-profile.yaml). "
                    f"Adopt into blueprints: {adopt_cmd}"
                )
            else:
                warnings.append(
                    f"WARN  Custom block '{name}' in {source_label} has {count} lines (> 160; will be routed). "
                    f"Adopt into blueprints: {adopt_cmd}"
                )
        elif count > 80:
            adopt_cmd = f"python3 .agents/skills/project-blueprints/scripts/blueprint.py adopt --from {source_label} --block {name} --area {area}"
            warnings.append(
                f"WARN  Custom block '{name}' in {source_label} has {count} lines (> 80). "
                f"Facts belong in blueprints (.agents/blueprints/) or the profile (.agents/project-profile.yaml). "
                f"Adopt into blueprints: {adopt_cmd}"
            )

    if total_lines > 600:
        if not allow_overflow:
            sys.exit(
                f"ERROR: {source_label} has {total_lines} total custom lines (> 600). "
                "Facts belong in blueprints (.agents/blueprints/) or the profile (.agents/project-profile.yaml)."
            )
        else:
            warnings.append(
                f"WARN  {source_label} has {total_lines} total custom lines (> 600; will be routed)."
            )
    elif total_lines > 300:
        warnings.append(
            f"WARN  {source_label} has {total_lines} total custom lines (> 300). "
            "Facts belong in blueprints (.agents/blueprints/) or the profile (.agents/project-profile.yaml)."
        )

    return warnings


def inject_custom_blocks(template_text: str, blocks: dict):
    """Inject preserved custom blocks into template_text. Return (merged_text, preserved_count, orphan_dict)."""
    norm = normalize_lf(template_text)
    orphan_blocks = {}
    preserved_count = 0

    for name, content in blocks.items():
        pattern = re.compile(rf"<!-- BEGIN CUSTOM: {re.escape(name)} -->\n?.*?<!-- END CUSTOM: {re.escape(name)} -->\n?", re.DOTALL)
        if pattern.search(norm):
            replacement = f"<!-- BEGIN CUSTOM: {name} -->\n{content}<!-- END CUSTOM: {name} -->\n"
            norm = pattern.sub(lambda _: replacement, norm, count=1)
            preserved_count += 1
        else:
            orphan_blocks[name] = content

    return norm, preserved_count, orphan_blocks


def append_orphans(orphans: list, root: Path) -> None:
    """Save orphan custom blocks to .agents/custom-orphans.md."""
    if not orphans:
        return
    orphans_file = root / ".agents" / "custom-orphans.md"
    orphans_file.parent.mkdir(parents=True, exist_ok=True)

    entries = []
    for rel_path, name, content in orphans:
        inner = content if (content.endswith("\n") or not content) else content + "\n"
        entry = (
            f"## {rel_path} (block: {name})\n\n"
            f"<!-- BEGIN CUSTOM: {name} -->\n"
            f"{inner}"
            f"<!-- END CUSTOM: {name} -->\n"
        )
        entries.append(entry)
        print(f"ORPHAN  Preserved custom block '{name}' from {rel_path} in .agents/custom-orphans.md")

    header = (
        "# Custom Block Orphans\n\n"
        "Preserved by render.py. Custom blocks whose file or block name no longer exists.\n\n"
    )
    if orphans_file.is_file():
        existing = orphans_file.read_text(encoding="utf-8")
        if not existing.startswith("# Custom Block Orphans"):
            existing = header + existing
        write_text_lf(orphans_file, existing.rstrip() + "\n\n" + "\n".join(entries))
    else:
        write_text_lf(orphans_file, header + "\n".join(entries))


def g(d, path, default=None):
    cur = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur if cur not in (None, "") else default


def rules(prof, *areas):
    out = []
    for r in prof.get("rules") or []:
        if r.get("area") in areas:
            tag = f" (enforced by {r['enforced_by']})" if r.get("enforced_by", "manual") != "manual" else ""
            out.append(f"- {r['text']}{tag} `[{r['id']}]`")
    return out


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return lines


def frontmatter(name, description):
    fm = yaml.safe_dump({"name": name, "description": description}, sort_keys=False, width=10000, allow_unicode=True)
    return f"---\n{fm}---\n"


def skill_build_ui(p, pn):
    name = g(p, "project.name")
    dirs = g(p, "design.component_dirs", [])
    tokens = g(p, "design.tokens_file")
    lines = [f"# How to build UI in {name}", "", "## Before you start", ""]
    n = 1
    if dirs:
        lines.append(f"{n}. Look in {', '.join(f'`{d}`' for d in dirs)} for an existing primitive. Use it. Extend it if a variant is missing. Do not create one off copies.")
        n += 1
    lines.append(f"{n}. Read the tokens in `{tokens}`. Use only those.")
    lines += ["", "## Blueprint", "",
              "Query codebase UI facts on demand:",
              "`python3 .agents/skills/project-blueprints/scripts/blueprint.py show --area ui --paths <files>`"]
    if g(p, "design.enabled"):
        first_dir = dirs[0] if dirs else "the first component folder"
        lines += [
            "",
            "## Form controls",
            "",
            "1. Use the themed primitive.",
            f"2. If none exists, build it first in `{first_dir}`, reusing existing low level widgets, as its own commit with loading, empty and error states where they apply, then use it.",
            "3. Never use a native browser control that a themed primitive covers.",
            "4. Read the Form controls table with the blueprint show command for the ui area before choosing a control."
        ]
    lines += ["", "## Rules", ""] + (rules(p, "design", "motion") or ["- No UI rules recorded. Add them to the profile."])
    lines += ["", "## Finish", "", f"Run `{g(p, 'commands.check', 'the project check command')}`."]
    if g(p, "design.enforced_by"):
        lines.append(f"`{g(p, 'design.enforced_by')}` enforces the design rules. Keep it passing.")
    if g(p, "responsive.enabled"):
        lines.append("Check the screen at the widths listed in `review-responsive-design`.")
    desc = (f"Use this skill whenever you build or change any UI in {name}: screens, components, sheets, charts, copy. "
            "Covers shared components, tokens, required states, motion and accessibility.")
    return "build-ui", desc, lines


def skill_design_system(p, pn):
    name = g(p, "project.name")
    tokens = g(p, "design.tokens_file")
    lines = [f"# {name} design system", "", f"All tokens live in `{tokens}`.", "",
             "## Blueprint", "",
             "Query codebase design tokens on demand:",
             "`python3 .agents/skills/project-blueprints/scripts/blueprint.py show --area tokens --paths <files>`", "",
             "## Token rules", ""]
    lines += rules(p, "tokens") or ["- No token rules recorded. Add them to the profile."]
    lines += ["", "## Changing a token", "",
              f"1. Edit `{tokens}` for every theme or mode.",
              "2. Check contrast in each mode.",
              f"3. Update `{g(p, 'docs.readme', 'README.md')}` if it lists tokens.",
              f"4. Run `{g(p, 'commands.check', 'the project check command')}`."]
    if g(p, "design.enforced_by"):
        lines.append(f"5. Confirm `{g(p, 'design.enforced_by')}` still passes.")
    desc = (f"Use this skill when you add or change tokens, global styles or shared UI primitives in {name}. "
            "Defines the palette, type scale, spacing, radius and motion tokens.")
    return "maintain-design-system", desc, lines


def skill_responsive(p, pn):
    name = g(p, "project.name")
    lo, hi = g(p, "responsive.min_width", 320), g(p, "responsive.max_width", 2560)
    bps = g(p, "responsive.breakpoints", [])
    lines = [f"# Responsive review for {name}", "", f"Support {lo}px to {hi}px. Touch targets are at least {g(p, 'responsive.touch_target_px', 44)}px on coarse pointers.", "",
             "## Blueprint", "",
             "Query codebase layout and breakpoint facts on demand:",
             "`python3 .agents/skills/project-blueprints/scripts/blueprint.py show --area layout --paths <files>`", ""]
    if bps:
        lines += ["## Breakpoints", ""] + table(["From (px)", "Layout"], [(b.get("from"), b.get("layout")) for b in bps]) + [""]
    lines += ["## Rules", ""] + (rules(p, "responsive") or ["- No responsive rules recorded. Add them to the profile."])
    widths = sorted({lo, *[b.get("from") for b in bps if isinstance(b.get("from"), int) and b.get("from")], hi})
    lines += ["", "## Verify", "", f"Open the app at {', '.join(str(w) for w in widths)} px. For each screen check: no horizontal scroll, no hidden content, no layout shift."]
    desc = (f"Use this skill when you build or audit layout in {name}. Covers breakpoints, navigation by size, "
            "touch targets, safe areas and zoom.")
    return "review-responsive-design", desc, lines


def skill_structure(p, pn):
    name = g(p, "project.name")
    layers = g(p, "structure.layers", [])
    lines = [f"# Directory structure of {name}", ""] + table(["Path", "Purpose"], [(f"`{l['path']}`", l["purpose"]) for l in layers])
    lines += ["", f"Tests: {'sit next to the file they test' if g(p, 'structure.tests') == 'colocated' else 'live in a tests folder'}."]
    root_allowed = g(p, "structure.root_allowed", [])
    if root_allowed:
        lines += ["", "## Root", "", "Allowed in the repo root: " + ", ".join(f"`{x}`" for x in root_allowed) + ". Put nothing else there."]
    r = rules(p, "structure")
    if r:
        lines += ["", "## Rules", ""] + r
    lines += ["", "## Before you add a file", "", "Search first with `repo-search`. Reuse or extend an existing file when it fits."]
    desc = f"Use this skill to place new files or move files in {name}. Describes each source layer and the root cleanliness rule."
    return "review-directory-structure", desc, lines


def skill_naming(p, pn):
    name = g(p, "project.name")
    items = g(p, "naming", [])
    lines = [f"# Naming in {name}", ""] + table(["Item", "Style", "Example"], [(n["item"], n["style"], f"`{n['example']}`") for n in items])
    r = rules(p, "naming")
    if r:
        lines += ["", "## Rules", ""] + r
    f = g(p, "git.commit_format")
    if f:
        lines += ["", f"Commit messages: `{f}`."]
    desc = f"Use this skill to name files, folders and identifiers in {name}."
    return "file-folder-naming", desc, lines


def skill_data(p, pn):
    name = g(p, "project.name")
    lines = [f"# Data rules for {name}", "",
             "## Blueprint", "",
             "Query codebase data models and storage facts on demand:",
             "`python3 .agents/skills/project-blueprints/scripts/blueprint.py show --area data --paths <files>`", ""]
    if g(p, "data.storage"):
        lines.append(f"Storage: {g(p, 'data.storage')}.")
    if g(p, "data.schema_source"):
        lines.append(f"Schema source: `{g(p, 'data.schema_source')}`. Read it before you change any data shape.")
    inv = g(p, "data.invariants", [])
    if inv:
        lines += ["", "## Invariants", ""] + [f"- {x}" for x in inv]
    prot = g(p, "data.protected", [])
    if prot:
        lines += ["", "## Ask before changing", ""] + [f"- {x}" for x in prot]
    r = rules(p, "data")
    if r:
        lines += ["", "## Rules", ""] + r
    desc = (f"Use this skill whenever you read, write or change data models, schemas, storage keys or payloads in {name}. "
            "Lists the invariants and the items that need approval to change.")
    return "review-db-structure", desc, lines


def has_data(p):
    return bool(g(p, "data.storage") or g(p, "data.invariants") or any(r.get("area") == "data" for r in p.get("rules") or []))


def build_skills(p, pn):
    out = []
    if g(p, "design.enabled"):
        out += [skill_build_ui(p, pn), skill_design_system(p, pn)]
    if g(p, "responsive.enabled"):
        out.append(skill_responsive(p, pn))
    out += [skill_structure(p, pn), skill_naming(p, pn)]
    if has_data(p):
        out.append(skill_data(p, pn))
    return out


def render_agents(p, pn, skill_names, root):
    name = g(p, "project.name")
    sdir = g(p, "docs.skills_dir") or ".agents/skills"
    s = p.get("stack") or {}
    stack = ", ".join(str(v) for k, v in s.items() if v and v != "none" and k in ("framework", "bundler", "styling", "backend", "database"))
    lines = [BANNER.format(profile=pn), "", f"# Agent Guidelines for {name}", "",
             f"{g(p, 'project.summary')}" + (f" Stack: {stack}." if stack else ""), "",
             f"Read the skill listed for each area before you touch it. Skills live in `{sdir}`. Facts live in `{pn}`. Rule details live in the skills. Do not copy them here. If your agent does not load skills on its own, open the skill file named in the table.", "",
             "## Areas", ""]
    sdir_path = root / sdir
    rows = []
    for sk, label in OPTIONAL_SKILLS:
        if (sdir_path / sk / "SKILL.md").exists():
            rows.append((label, f"`{sk}`"))
    rows.append(("Any change", "`audit-and-planning`, `repo-search`"))
    if "build-ui" in skill_names:
        rows.append(("UI and tokens", "`build-ui`, `maintain-design-system`"))
    if "review-responsive-design" in skill_names:
        rows.append(("Layout", "`review-responsive-design`"))
    rows.append(("File placement and names", "`review-directory-structure`, `file-folder-naming`"))
    if "review-db-structure" in skill_names:
        rows.append(("Data and storage", "`review-db-structure`"))
    rows += [("Verify", "`targeted-module-testing`"), ("Commit", "`atomic-commits`"), ("Docs", "`sync-skills-and-docs`")]
    lines += table(["Area", "Skill"], rows)
    lines += ["", "## Pipeline", "",
              "1. Audit: search before you edit.", "2. Plan: small atomic steps.", "3. Build.", "4. Verify.",
              "5. Commit.", "6. Sync docs and the repo map.", "7. Report open questions and known issues.", ""]
    project_rules = rules(p, "process", "security", "verify", "git", "docs")
    if project_rules:
        lines += ["## Project rules", ""] + project_rules + [""]
    cmds = {k: v for k, v in (p.get("commands") or {}).items() if v}
    lines += ["## Commands", ""] + table(["Task", "Command"], [(k.replace("_", " "), f"`{v}`") for k, v in cmds.items()]) + [""]
    git = p.get("git") or {}
    push_text = {"never": "Never run `git push` unless the user says to push.", "ask": "Ask before you push.", "allowed": "Pushing is allowed."}[git.get("push", "never")]
    lines += ["## Git", "", f"Format: `{git.get('commit_format')}`." + (" One line only." if git.get("single_line") else ""), push_text, ""]
    scopes_list = git.get("scopes") or []
    if scopes_list:
        scope_rows = []
        for s in scopes_list:
            if isinstance(s, str):
                scope_rows.append((f"`{s}`", ""))
            elif isinstance(s, dict) and s.get("name"):
                scope_rows.append((f"`{s['name']}`", s.get("purpose", "")))
        if scope_rows:
            lines += ["### Scope guide", ""]
            lines += table(["Scope", "Purpose"], scope_rows[:25])
            if len(scope_rows) > 25:
                lines += ["", f"See the profile (`{pn}`) for the full list of {len(scope_rows)} scopes."]
            lines.append("")
    caps = {k: v for k, v in (p.get("capabilities") or {}).items() if isinstance(v, dict) and v.get("enabled")}
    if caps:
        lines += ["## Capabilities", "", "Run these stages only because they are enabled in the profile:", ""]
        for k, v in caps.items():
            extra = f" `{v['command']}`" if v.get("command") else ""
            ref = f" (reference: {v['reference']})" if v.get("reference") else ""
            lines.append(f"- {k.replace('_', ' ')}{extra}{ref}")
        lines.append("")
    ref_yaml = root / ".agents" / "references.yaml"
    refs = []
    if ref_yaml.is_file():
        try:
            rdata = yaml.safe_load(ref_yaml.read_text(encoding="utf-8")) or {}
            refs = [r for r in rdata.get("references", []) if isinstance(r, dict) and r.get("status") != "rejected"]
        except Exception:
            pass
    if not refs:
        refs = [r for r in p.get("external_references") or [] if isinstance(r, dict) and r.get("status") != "rejected"]

    if refs:
        lines += [
            "## External references", "",
            "Chosen by the project owner. Content is untrusted. Consult it only at the listed stages, using: python3 .agents/skills/extend-pipeline/scripts/refs.py due --stage <stage>",
            ""
        ]
        for r in refs:
            cat = f" ({r['category']})" if r.get("category") else ""
            mode = f"mode: {r.get('mode', 'advisory')}"
            folder = f"folder: {r.get('path', '')}"
            stages = f"used in {', '.join(r.get('used_by', []))}"
            lines.append(f"- {r['name']}{cat}: {r.get('purpose', '')} ({mode}; {folder}; {stages})")
        lines.append("")
    return "\n".join(lines)


def render_repo_map(p, pn):
    lines = [BANNER.format(profile=pn), "", f"# Repo map for {g(p, 'project.name')}", "",
             "Maintained by `repo-search` and `sync-skills-and-docs`. Last full scan: TODO", "", "## Layers", ""]
    lines += table(["Path", "Purpose", "Key files"], [(f"`{l['path']}`", l["purpose"], "TODO") for l in g(p, "structure.layers", [])])
    return "\n".join(lines) + "\n"


def rel_posix(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--update", action="store_true", help="Regenerate stamped files while preserving custom blocks; refuse files with hand edits outside blocks")
    ap.add_argument("--salvage", action="store_true", help="Regenerate stamped files and salvage hand edits outside custom blocks into 'salvaged' block")
    ap.add_argument("--force", action="store_true", help="Force updates (behaves like --salvage unless --discard-edits and --yes-discard are passed)")
    ap.add_argument("--overwrite-unstamped", action="store_true", help="Allow --force to overwrite unstamped files")
    ap.add_argument("--upgrade-unstamped", action="store_true", help="Upgrade unstamped convention skills carrying old banner to stamped template while salvaging hand edits")
    ap.add_argument("--migrate-custom", action="store_true", help="Wrap unstamped file body into 'legacy' custom block and render generated skill around it")
    ap.add_argument("--discard-edits", action="store_true", help="Discard hand edits outside custom blocks (requires --yes-discard)")
    ap.add_argument("--yes-discard", action="store_true", help="Confirm discarding hand edits outside custom blocks")
    ap.add_argument("--allow-dirty", action="store_true", help="Allow overwrite/salvage/migration despite uncommitted git changes")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.discard_edits and not a.yes_discard:
        sys.exit("ERROR: --discard-edits requires --yes-discard.")

    root = Path(a.root).resolve()
    prof_path = Path(a.profile).resolve()
    if not prof_path.is_file():
        sys.exit(f"Profile not found: {prof_path}")
    p = yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {}
    pn = rel_posix(prof_path, root)

    skills_dir = root / (g(p, "docs.skills_dir") or ".agents/skills")
    generated = build_skills(p, pn)
    names = {n for n, _, _ in generated}

    # Prepare targets: (dest_path, raw_template, kind)
    targets = []
    notes_block = "\n<!-- BEGIN CUSTOM: notes -->\n<!-- END CUSTOM: notes -->\n"

    for name, desc, body in generated:
        raw_body = frontmatter(name, desc) + "\n" + BANNER.format(profile=pn) + "\n\n" + "\n".join(body) + notes_block
        dest = skills_dir / name / "SKILL.md"
        targets.append((dest, raw_body, "skill"))

    agents_file = root / (g(p, "docs.agents_file") or "AGENTS.md")
    agents_raw = render_agents(p, pn, names, root) + notes_block
    targets.append((agents_file, agents_raw, "agents"))

    repo_map_path = g(p, "docs.repo_map")
    if repo_map_path:
        repo_map_dest = root / repo_map_path
        repo_map_raw = render_repo_map(p, pn) + notes_block
        targets.append((repo_map_dest, repo_map_raw, "repo_map"))

    active_dest_paths = {dest for dest, _, _ in targets}

    created = []
    updated = []
    refused = []
    skipped = []
    all_orphans = []
    all_warnings = []

    # Dirty tree guard: check existing target files
    existing_targets = [dest for dest, _, _ in targets if dest.is_file()]
    if (a.update or a.salvage or a.force or a.migrate_custom or a.upgrade_unstamped) and existing_targets:
        check_git_dirty(root, existing_targets, a.allow_dirty)

    # Pre-flight check for --update: transactional validation
    if a.update and not a.salvage and not a.force:
        refusal_diffs = {}
        for dest, raw_tmpl, kind in targets:
            if not dest.is_file():
                continue
            disk_text = normalize_lf(dest.read_text(encoding="utf-8"))
            m = STAMP_RE.search(disk_text)
            if not m:
                # Unstamped files are processed per file and skipped with exit code 3 during --update
                continue

            stamp_hash = m.group(1)
            disk_body_hash = compute_body_hash(disk_text)
            disk_blocks = extract_custom_blocks(disk_text, rel_posix(dest, root))
            warns = validate_custom_blocks(disk_blocks, rel_posix(dest, root))
            all_warnings.extend(warns)

            if disk_body_hash != stamp_hash:
                # Hand edits detected outside custom blocks
                # Compute unified diff
                merged_candidate, _, _ = inject_custom_blocks(raw_tmpl, disk_blocks)
                new_hash = compute_body_hash(raw_tmpl)
                candidate_stamped = stamp_text(merged_candidate, new_hash)

                diff_lines = list(difflib.unified_diff(
                    disk_text.splitlines(keepends=True),
                    candidate_stamped.splitlines(keepends=True),
                    fromfile=f"{rel_posix(dest, root)} (current)",
                    tofile=f"{rel_posix(dest, root)} (expected clean)",
                ))
                refusal_diffs[dest] = "".join(diff_lines)
                refused.append((dest, "hand edits outside custom blocks"))

        if refused:
            for w in all_warnings:
                print(w)
            for dest, diff in refusal_diffs.items():
                print(f"\nREFUSED {rel_posix(dest, root)} (hand edits outside custom blocks):\n")
                print(diff)
            print("\nRender summary:")
            print("  created:   none")
            print("  updated:   none")
            print("  refused:")
            for r, reason in refused:
                print(f"    - {rel_posix(r, root)} ({reason})")
            print("  skipped:   none")
            sys.exit(1)

    # Process all targets
    for dest, raw_tmpl, kind in targets:
        rel_label = rel_posix(dest, root)
        if not dest.is_file():
            # Fresh file
            body_hash = compute_body_hash(raw_tmpl)
            final_content = stamp_text(raw_tmpl, body_hash)
            if not a.dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                write_text_lf(dest, final_content)
            created.append(dest)
            prefix = "DRY RUN " if a.dry_run else ""
            print(f"{prefix}WROTE   {rel_label}")
            continue

        # File exists
        disk_text = normalize_lf(dest.read_text(encoding="utf-8"))
        stamp_m = STAMP_RE.search(disk_text)

        if not stamp_m:
            # Unstamped file
            has_old_banner = bool(OLD_BANNER_RE.search(disk_text))
            rec_msg = "use --upgrade-unstamped to upgrade" if has_old_banner else "use --migrate-custom to wrap in legacy block"

            if a.update and not a.upgrade_unstamped and not a.migrate_custom and not a.force:
                skipped.append((dest, f"unstamped file exists; {rec_msg}"))
                print(f"SKIPPED {rel_label} (unstamped; {rec_msg})")
                continue

            if a.upgrade_unstamped:
                if not OLD_BANNER_RE.search(disk_text):
                    skipped.append((dest, "unstamped file has no old generator banner"))
                    print(f"SKIPPED {rel_label} (unstamped; no generator banner)")
                    continue

                disk_blocks = extract_custom_blocks(disk_text, rel_label)
                clean_disk = strip_custom_blocks(strip_stamp(disk_text))
                clean_tmpl = strip_custom_blocks(raw_tmpl)
                salvaged_lines = compute_salvaged_lines(clean_tmpl, clean_disk)
                salvaged_lines = [l for l in salvaged_lines if not OLD_BANNER_RE.search(l)]

                salvaged_count = 0
                salvaged_body = ""
                if salvaged_lines:
                    salvaged_body = "\n".join(salvaged_lines).strip() + "\n"
                    scan_secrets(salvaged_body, rel_label)
                    header = "<!-- Salvaged hand edits from unstamped file -->\n"
                    full_content = header + salvaged_body
                    if "salvaged" in disk_blocks:
                        disk_blocks["salvaged"] = disk_blocks["salvaged"].rstrip() + "\n\n" + salvaged_body
                    else:
                        disk_blocks["salvaged"] = full_content
                    salvaged_count = len(salvaged_lines)

                # Ensure special custom blocks (salvaged, legacy) are present in template before injection
                for special_block in ("legacy", "salvaged"):
                    if special_block in disk_blocks and f"<!-- BEGIN CUSTOM: {special_block} -->" not in raw_tmpl:
                        marker = f"<!-- BEGIN CUSTOM: {special_block} -->\n<!-- END CUSTOM: {special_block} -->\n"
                        if "<!-- BEGIN CUSTOM: notes -->" in raw_tmpl:
                            raw_tmpl = raw_tmpl.replace("<!-- BEGIN CUSTOM: notes -->", marker + "<!-- BEGIN CUSTOM: notes -->", 1)
                        else:
                            raw_tmpl = raw_tmpl.rstrip() + "\n\n" + marker

                merged, n_pres, orphans = inject_custom_blocks(raw_tmpl, disk_blocks)
                for oname, ocontent in orphans.items():
                    all_orphans.append((rel_label, oname, ocontent))

                new_body_hash = compute_body_hash(raw_tmpl)
                final_content = stamp_text(merged, new_body_hash)
                if not a.dry_run:
                    write_text_lf(dest, final_content)
                    if salvaged_count > 160 or (salvaged_lines and has_large_table_or_fenced_block(salvaged_body)):
                        route_overflow(root, dest, "salvaged", disk_blocks["salvaged"], rel_label)

                log_render_action(root, rel_label, "upgrade-unstamped", salvaged_count)
                updated.append((dest, n_pres, salvaged_count))
                prefix = "DRY RUN " if a.dry_run else ""
                print(f"{prefix}UPGRADED {rel_label} (preserved {n_pres} block(s), salvaged {salvaged_count} line(s))")
                continue

            elif a.migrate_custom:
                existing_body = disk_text
                scan_secrets(existing_body, rel_label)
                lines = existing_body.splitlines()
                lines_count = len(lines)
                needs_adopt = lines_count > 80 or has_large_table_or_fenced_block(existing_body)

                # Wrap existing body in legacy custom block
                legacy_header = "<!-- Legacy body before Build Forge migration -->\n"
                full_legacy = legacy_header + existing_body
                disk_blocks = {"legacy": full_legacy}

                # Ensure legacy marker in raw_tmpl
                marker = "<!-- BEGIN CUSTOM: legacy -->\n<!-- END CUSTOM: legacy -->\n"
                if "<!-- BEGIN CUSTOM: notes -->" in raw_tmpl:
                    raw_tmpl = raw_tmpl.replace("<!-- BEGIN CUSTOM: notes -->", marker + "<!-- BEGIN CUSTOM: notes -->", 1)
                else:
                    raw_tmpl = raw_tmpl.rstrip() + "\n\n" + marker

                merged, n_pres, _ = inject_custom_blocks(raw_tmpl, disk_blocks)
                new_body_hash = compute_body_hash(raw_tmpl)
                final_content = stamp_text(merged, new_body_hash)
                if not a.dry_run:
                    write_text_lf(dest, final_content)

                if needs_adopt and not a.dry_run:
                    route_overflow(root, dest, "legacy", existing_body, rel_label)

                log_render_action(root, rel_label, "migrate-custom", lines_count)
                updated.append((dest, 1, 0))
                print(f"MIGRATED {rel_label} (wrapped in legacy custom block, {lines_count} lines)")
                continue

            elif a.force and a.overwrite_unstamped:
                if not (a.discard_edits and a.yes_discard):
                    refused.append((dest, "overwriting unstamped content requires --discard-edits and --yes-discard"))
                    print(f"REFUSED {rel_label} (overwriting unstamped content requires --discard-edits and --yes-discard)")
                    continue

                discarded = disk_text.splitlines()
                discarded_count = len(discarded)
                if discarded:
                    print(f"DISCARDED {discarded_count} line(s) from {rel_label}:")
                    for d in discarded:
                        print(f"  - {d}")
                body_hash = compute_body_hash(raw_tmpl)
                final_content = stamp_text(raw_tmpl, body_hash)
                if not a.dry_run:
                    write_text_lf(dest, final_content)
                updated.append((dest, 0, 0))
                print(f"OVERWROTE {rel_label} (unstamped; forced with --overwrite-unstamped)")
                continue

            elif not a.force and not a.update and not a.salvage and kind == "agents":
                gen_dest = dest.with_name(dest.stem + ".generated" + dest.suffix)
                body_hash = compute_body_hash(raw_tmpl)
                final_content = stamp_text(raw_tmpl, body_hash)
                if not a.dry_run:
                    write_text_lf(gen_dest, final_content)
                created.append(gen_dest)
                print(f"NOTE  {dest.name} exists. Router written to {gen_dest.name}. Merge it by hand.")
                continue

            else:
                has_banner = bool(OLD_BANNER_RE.search(disk_text))
                rec = "use --upgrade-unstamped to upgrade" if has_banner else "use --migrate-custom to wrap in legacy block"
                skipped.append((dest, f"unstamped file exists; {rec}"))
                print(f"SKIPPED {rel_label} (unstamped; {rec})")
                continue

        # Stamped file
        stamp_hash = stamp_m.group(1)
        disk_body_hash = compute_body_hash(disk_text)
        disk_blocks = extract_custom_blocks(disk_text, rel_label)

        is_salvage_run = a.salvage or a.force
        warns = validate_custom_blocks(disk_blocks, rel_label, allow_overflow=is_salvage_run)
        all_warnings.extend(warns)
        has_hand_edits = (disk_body_hash != stamp_hash)

        if not a.update and not a.force and not a.salvage and not a.upgrade_unstamped:
            # Plain render.py: default behavior is skip existing files
            if kind == "agents":
                gen_dest = dest.with_name(dest.stem + ".generated" + dest.suffix)
                body_hash = compute_body_hash(raw_tmpl)
                final_content = stamp_text(raw_tmpl, body_hash)
                if not a.dry_run:
                    write_text_lf(gen_dest, final_content)
                created.append(gen_dest)
                print(f"NOTE  {dest.name} exists. Router written to {gen_dest.name}. Merge it by hand.")
            else:
                skipped.append((dest, "exists; use --update or --salvage"))
                print(f"SKIPPED {rel_label} (exists; use --update or --salvage to overwrite)")
            continue

        salvaged_count = 0
        if has_hand_edits:
            if a.discard_edits and a.yes_discard:
                clean_disk = strip_custom_blocks(strip_stamp(disk_text))
                clean_tmpl = strip_custom_blocks(raw_tmpl)
                discarded = compute_salvaged_lines(clean_tmpl, clean_disk)
                if discarded:
                    print(f"DISCARDED {len(discarded)} line(s) from {rel_label}:")
                    for d in discarded:
                        print(f"  - {d}")
            elif is_salvage_run:
                clean_disk = strip_custom_blocks(strip_stamp(disk_text))
                clean_tmpl = strip_custom_blocks(raw_tmpl)
                salvaged_lines = compute_salvaged_lines(clean_tmpl, clean_disk)
                if salvaged_lines:
                    salvaged_body = "\n".join(salvaged_lines) + "\n"
                    scan_secrets(salvaged_body, rel_label)
                    header = "<!-- Salvaged hand edits outside custom blocks -->\n"
                    full_content = header + salvaged_body
                    if "salvaged" in disk_blocks:
                        disk_blocks["salvaged"] = disk_blocks["salvaged"].rstrip() + "\n\n" + salvaged_body
                    else:
                        disk_blocks["salvaged"] = full_content
                    salvaged_count = len(salvaged_lines)
                    log_render_action(root, rel_label, "salvage", salvaged_count)
                    print(f"SALVAGED {salvaged_count} line(s) from {rel_label}")

        # Ensure special custom blocks (salvaged, legacy) are present in template before injection
        for special_block in ("legacy", "salvaged"):
            if special_block in disk_blocks and f"<!-- BEGIN CUSTOM: {special_block} -->" not in raw_tmpl:
                marker = f"<!-- BEGIN CUSTOM: {special_block} -->\n<!-- END CUSTOM: {special_block} -->\n"
                if "<!-- BEGIN CUSTOM: notes -->" in raw_tmpl:
                    raw_tmpl = raw_tmpl.replace("<!-- BEGIN CUSTOM: notes -->", marker + "<!-- BEGIN CUSTOM: notes -->", 1)
                else:
                    raw_tmpl = raw_tmpl.rstrip() + "\n\n" + marker

        # Inject custom blocks and write updated stamped file
        merged, n_pres, orphans = inject_custom_blocks(raw_tmpl, disk_blocks)
        for oname, ocontent in orphans.items():
            all_orphans.append((rel_label, oname, ocontent))

        new_body_hash = compute_body_hash(raw_tmpl)
        final_content = stamp_text(merged, new_body_hash)
        if not a.dry_run:
            write_text_lf(dest, final_content)

        # Route overflow blocks if in salvage run
        if (is_salvage_run or a.upgrade_unstamped) and not a.dry_run:
            for bname, bcontent in list(disk_blocks.items()):
                blines = bcontent.splitlines()
                if len(blines) > 160:
                    route_overflow(root, dest, bname, bcontent, rel_label)

        updated.append((dest, n_pres, salvaged_count))
        prefix = "DRY RUN " if a.dry_run else ""
        if salvaged_count > 0:
            print(f"{prefix}UPDATED {rel_label} (preserved {n_pres} block(s), salvaged {salvaged_count} line(s))")
        else:
            print(f"{prefix}UPDATED {rel_label} (preserved {n_pres} block(s))")

    # Check for inactive convention skills that have custom blocks
    for skill_name in CONVENTION_SKILLS:
        skill_file = skills_dir / skill_name / "SKILL.md"
        if skill_file.is_file() and skill_file not in active_dest_paths:
            content = skill_file.read_text(encoding="utf-8")
            blocks = extract_custom_blocks(content, rel_posix(skill_file, root))
            for bname, bcontent in blocks.items():
                if bcontent.strip():
                    all_orphans.append((rel_posix(skill_file, root), bname, bcontent))

    if not a.dry_run:
        append_orphans(all_orphans, root)

    for w in all_warnings:
        print(w)

    missing = [s for s in PROCESS_SKILLS if not (skills_dir / s / "SKILL.md").exists()]
    if missing:
        print("NOTE  Process skills not found in the skills dir: " + ", ".join(missing))
    print("If your agent does not read .agents/skills, run: npx @v1006/build-forge link")

    print("\nRender summary:")
    if created:
        print("  created:")
        for c in created:
            print(f"    - {rel_posix(c, root)}")
    else:
        print("  created:   none")

    if updated:
        print("  updated:")
        for entry in updated:
            u = entry[0]
            n_blk = entry[1]
            n_salv = entry[2] if len(entry) > 2 else 0
            if n_salv > 0:
                print(f"    - {rel_posix(u, root)} (preserved {n_blk} block(s), salvaged {n_salv} line(s))")
            else:
                print(f"    - {rel_posix(u, root)} (preserved {n_blk} block(s))")
    else:
        print("  updated:   none")

    if refused:
        print("  refused:")
        for r, reason in refused:
            print(f"    - {rel_posix(r, root)} ({reason})")
    else:
        print("  refused:   none")

    if skipped:
        print("  skipped:")
        for s, reason in skipped:
            print(f"    - {rel_posix(s, root)} ({reason})")
    else:
        print("  skipped:   none")

    if refused:
        sys.exit(1)

    if a.update and skipped:
        sys.exit(3)


if __name__ == "__main__":
    main()
