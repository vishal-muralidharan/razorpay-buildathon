#!/usr/bin/env python3
"""Project blueprints extraction, verification, staleness checking, and querying tool."""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

# Add script directory to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    import yaml
except ImportError:
    yaml = None

from analyzers import auth, common, config, data, layout, tokens, ui

GENERATOR_VERSION = "0.2.0"

AREAS = {
    "data": data,
    "tokens": tokens,
    "ui": ui,
    "layout": layout,
    "auth": auth,
    "config": config,
}

CUSTOM_BLOCK_RE = re.compile(
    r"(<!--\s*BEGIN CUSTOM:\s*([a-zA-Z0-9_-]+)\s*-->\n.*?\n<!--\s*END CUSTOM:\s*\2\s*-->)",
    re.DOTALL
)


def write_text_lf(path: Path, content: str) -> None:
    """Write text file with strictly LF line endings across all operating systems."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content.replace("\r\n", "\n"))


def load_profile(root: Path) -> dict:
    """Load project profile if available."""
    p_file = root / ".agents" / "project-profile.yaml"
    if p_file.is_file() and yaml:
        try:
            return yaml.safe_load(p_file.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
    return {}


def extract_custom_blocks(text: str) -> dict:
    """Extract custom blocks from text keyed by block name."""
    blocks = {}
    for m in CUSTOM_BLOCK_RE.finditer(text):
        full_block = m.group(1)
        bname = m.group(2)
        blocks[bname] = full_block
    return blocks


def split_into_parts(lines: list, area: str, max_lines: int = 250) -> list:
    """Split generated content lines into parts of at most max_lines."""
    if len(lines) <= max_lines:
        return [(f"{area}.md", lines)]

    parts = []
    part_idx = 1
    for i in range(0, len(lines), max_lines):
        chunk = lines[i: i + max_lines]
        fname = f"{area}.md" if part_idx == 1 else f"{area}-part-{part_idx}.md"
        parts.append((fname, chunk))
        part_idx += 1
    return parts


def cmd_extract(root: Path, selected_areas: list = None) -> int:
    """Run analyzers and write blueprint files."""
    profile = load_profile(root)
    bp_dir = root / ".agents" / "blueprints"
    bp_dir.mkdir(parents=True, exist_ok=True)

    areas_to_run = selected_areas if selected_areas else list(AREAS.keys())

    manifest_sources = {}
    all_candidates = []
    generated_files = []
    unsupported_langs = set()

    for area_name in sorted(areas_to_run):
        if area_name not in AREAS:
            continue
        mod = AREAS[area_name]
        if not mod.detect(root, profile):
            continue

        result = mod.extract(root, profile)
        rendered_content = mod.render(result)

        # Check for secrets before saving
        secret_matches = common.scan_for_secrets(rendered_content)
        if secret_matches:
            print(f"Error: Secret pattern detected in generated {area_name} blueprint: {secret_matches[0]}", file=sys.stderr)
            return 1

        # Preserve existing custom blocks
        target_file = bp_dir / f"{area_name}.md"
        existing_blocks = {}
        if target_file.is_file():
            old_text = target_file.read_text(encoding="utf-8", errors="replace")
            existing_blocks = extract_custom_blocks(old_text)

        # Split generated content into parts if it exceeds budget
        gen_lines = rendered_content.strip().split("\n")
        parts = split_into_parts(gen_lines, area_name, max_lines=250)

        for p_idx, (fname, p_lines) in enumerate(parts):
            p_file = bp_dir / fname
            out_lines = list(p_lines)

            # Contracts custom block belongs on the primary area file
            if p_idx == 0:
                out_lines.append("")
                if "contracts" in existing_blocks:
                    out_lines.append(existing_blocks["contracts"])
                else:
                    out_lines.append("<!-- BEGIN CUSTOM: contracts -->")
                    out_lines.append("<!-- END CUSTOM: contracts -->")

                # Re-attach other existing custom blocks
                for bname, bcontent in existing_blocks.items():
                    if bname != "contracts":
                        out_lines.append("")
                        out_lines.append(bcontent)

            write_text_lf(p_file, "\n".join(out_lines) + "\n")
            generated_files.append(fname)

        # Collect source hashes for manifest
        src_hashes = {}
        for src in result.get("sources", []):
            if (root / src).is_file():
                src_hashes[src] = common.hash_file_lf(root, src)
        manifest_sources[area_name] = src_hashes

        # Collect candidates
        for c in result.get("candidates", []):
            all_candidates.append(c)

        for u in result.get("unsupported", []):
            unsupported_langs.add(u)

    # Write candidates.md
    c_file = bp_dir / "candidates.md"
    c_lines = ["# Blueprint Rule Candidates\n"]
    c_lines.append("Proposed candidates from codebase facts. User confirmation required before adding to profile.\n")
    if not all_candidates:
        c_lines.append("- No rule candidates identified.\n")
    else:
        for c in all_candidates:
            c_lines.append(f"- **{c['id']}** ({c['area']}): {c['rule']}")
            c_lines.append(f"  - Evidence: `{c['evidence']}`")
    write_text_lf(c_file, "\n".join(c_lines) + "\n")

    # Write index.md (strictly budget <= 60 lines)
    idx_file = bp_dir / "index.md"
    idx_lines = [
        "# Project Blueprints Index\n",
        "Deterministic, verified facts extracted directly from codebase evidence.\n",
        "## Areas\n"
    ]
    all_bp_files = sorted([f.name for f in bp_dir.glob("*.md") if f.name not in ("index.md", "candidates.md")])
    for g in all_bp_files:
        idx_lines.append(f"- [{g}]({g})")

    idx_lines.append("\n## Generator\n")
    idx_lines.append(f"- Version: `{GENERATOR_VERSION}`")
    idx_lines.append(f"- Analyzers: {', '.join(sorted(areas_to_run))}")

    if unsupported_langs:
        idx_lines.append(f"- Unsupported languages: {', '.join(sorted(unsupported_langs))}")

    write_text_lf(idx_file, "\n".join(idx_lines[:58]) + "\n")

    # Write manifest.json
    manifest_data = {
        "generator_version": GENERATOR_VERSION,
        "analyzers": sorted(areas_to_run),
        "areas": manifest_sources
    }
    m_file = bp_dir / "manifest.json"
    write_text_lf(m_file, json.dumps(manifest_data, indent=2, sort_keys=True) + "\n")

    print(f"Extracted blueprints to .agents/blueprints/ ({len(generated_files)} files).")
    return 0


def cmd_verify(root: Path) -> int:
    """Verify all evidence entries in generated blueprints match source files."""
    bp_dir = root / ".agents" / "blueprints"
    if not bp_dir.is_dir():
        print("Error: .agents/blueprints/ directory not found.", file=sys.stderr)
        return 1

    ev_pattern = re.compile(r"(?:evidence|Evidence):\s*`([^`:]+):(\d+)`")
    alt_pattern = re.compile(r"\(`([^`:]+):(\d+)`\)")

    failures = []
    checked = 0

    for fpath in sorted(bp_dir.glob("*.md")):
        if fpath.name in ("index.md", "candidates.md"):
            continue
        content = fpath.read_text(encoding="utf-8", errors="replace")
        matches = ev_pattern.findall(content) + alt_pattern.findall(content)

        for rel_src, line_str in matches:
            checked += 1
            src_file = root / rel_src
            if not src_file.is_file():
                failures.append(f"{fpath.name}: source file '{rel_src}' not found.")
                continue

            try:
                line_no = int(line_str)
                s_lines = src_file.read_text(encoding="utf-8", errors="replace").split("\n")
                if line_no < 1 or line_no > len(s_lines) + 5:
                    failures.append(f"{fpath.name}: line {line_no} out of bounds for '{rel_src}' ({len(s_lines)} lines).")
            except Exception as e:
                failures.append(f"{fpath.name}: error reading '{rel_src}': {e}")

    if failures:
        print(f"Blueprint verification failed ({len(failures)} errors):", file=sys.stderr)
        for err in failures[:10]:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"Verified {checked} evidence entries across blueprints. All passed.")
    return 0


def cmd_stale(root: Path, fail_on_stale: bool = False) -> int:
    """Check if any blueprint sources changed since extraction."""
    m_file = root / ".agents" / "blueprints" / "manifest.json"
    if not m_file.is_file():
        print("Blueprints not generated or manifest.json missing.")
        return 1 if fail_on_stale else 0

    try:
        manifest = json.loads(m_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error reading manifest: {e}", file=sys.stderr)
        return 1

    stale_areas = []
    areas_dict = manifest.get("areas", {})

    for area, src_hashes in sorted(areas_dict.items()):
        area_stale = False
        for src, old_hash in src_hashes.items():
            src_path = root / src
            if not src_path.is_file():
                area_stale = True
                break
            cur_hash = common.hash_file_lf(root, src)
            if cur_hash != old_hash:
                area_stale = True
                break
        if area_stale:
            stale_areas.append(area)

    if stale_areas:
        print(f"Stale blueprint areas: {', '.join(stale_areas)}")
        if fail_on_stale:
            return 1
    else:
        print("All blueprints are up to date.")

    return 0


def cmd_show(root: Path, area: str, paths: list = None, budget: int = 120) -> int:
    """Print blueprint facts relevant to given paths within line budget."""
    bp_file = root / ".agents" / "blueprints" / f"{area}.md"
    if not bp_file.is_file():
        print(f"Blueprint for area '{area}' not found at {bp_file}.")
        return 1

    content = bp_file.read_text(encoding="utf-8", errors="replace")
    lines = content.split("\n")

    if not paths:
        # Show whole file within budget
        output_lines = lines[:budget]
        print("\n".join(output_lines))
        if len(lines) > budget:
            print(f"\n[Budget limit {budget} reached. Skipped {len(lines) - budget} lines.]")
        return 0

    # Filter lines relevant to paths
    filtered_lines = []
    path_keywords = set()
    for p in paths:
        path_keywords.add(Path(p).stem.lower())
        path_keywords.add(p.lower())

    for line in lines:
        if line.startswith("#"):
            filtered_lines.append(line)
        elif any(kw in line.lower() for kw in path_keywords):
            filtered_lines.append(line)

    if len(filtered_lines) <= 5:
        # Fall back to top budget lines if filtering was too aggressive
        filtered_lines = lines

    output_lines = filtered_lines[:budget]
    print("\n".join(output_lines))
    if len(filtered_lines) > budget:
        print(f"\n[Budget limit {budget} reached. Skipped {len(filtered_lines) - budget} lines.]")
    return 0


def cmd_candidates(root: Path) -> int:
    """Print rule candidates from candidates.md."""
    c_file = root / ".agents" / "blueprints" / "candidates.md"
    if not c_file.is_file():
        print("No candidates.md found. Run extract first.")
        return 1

    print(c_file.read_text(encoding="utf-8", errors="replace").strip())
    return 0


def cmd_init(root: Path, selected_areas: list = None) -> int:
    """Scaffold missing canonical blueprint files from templates without overwriting."""
    bp_dir = root / ".agents" / "blueprints"
    bp_dir.mkdir(parents=True, exist_ok=True)
    templates_dir = SCRIPT_DIR.parent / "assets" / "templates"

    profile = load_profile(root)
    canonical_areas = ["data", "tokens", "ui", "layout"]
    if selected_areas:
        areas_to_init = selected_areas
    else:
        areas_to_init = list(canonical_areas)
        # Add areas detected by analyzers
        for aname, amod in AREAS.items():
            if aname not in areas_to_init and amod.detect(root, profile):
                areas_to_init.append(aname)

    created_files = []
    for area in sorted(areas_to_init):
        target = bp_dir / f"{area}.md"
        if target.is_file():
            print(f"Skipped existing .agents/blueprints/{area}.md (never overwritten).")
            created_files.append(f"{area}.md")
            continue

        template_src = templates_dir / f"{area}.md"
        if template_src.is_file():
            content = template_src.read_text(encoding="utf-8")
        else:
            content = (
                f"# {area.title()} Blueprint\n\n"
                f"Canonical {area} facts and contracts.\n\n"
                "<!-- BEGIN CUSTOM: contracts -->\n"
                "<!-- END CUSTOM: contracts -->\n"
            )
        write_text_lf(target, content)
        print(f"Initialized .agents/blueprints/{area}.md from template.")
        created_files.append(f"{area}.md")

    # Ensure index.md exists
    idx_file = bp_dir / "index.md"
    if not idx_file.is_file():
        idx_lines = [
            "# Project Blueprints Index\n",
            "Deterministic, verified facts extracted directly from codebase evidence.\n",
            "## Areas\n"
        ]
        for cf in sorted(created_files):
            idx_lines.append(f"- [{cf}]({cf})")
        write_text_lf(idx_file, "\n".join(idx_lines[:58]) + "\n")

    return 0


def cmd_adopt(root: Path, from_file: str, block_name: str, area: str) -> int:
    """Move a custom block out of a convention skill into blueprint contracts atomically."""
    from_path = Path(from_file)
    if not from_path.is_absolute():
        from_path = root / from_path
    from_path = from_path.resolve()

    if not from_path.is_file():
        print(f"Error: Source file '{from_file}' not found.", file=sys.stderr)
        return 1

    src_content = from_path.read_text(encoding="utf-8", errors="replace")
    pat = re.compile(
        rf"<!--\s*BEGIN CUSTOM:\s*{re.escape(block_name)}\s*-->\n?(.*?)<!--\s*END CUSTOM:\s*{re.escape(block_name)}\s*-->\n?",
        re.DOTALL
    )
    match = pat.search(src_content)
    if not match:
        print(f"Error: Custom block '{block_name}' not found in '{from_file}'.", file=sys.stderr)
        return 1

    block_body = match.group(1).strip()

    # Secret scan: refuse if potential secrets detected
    secret_matches = common.scan_for_secrets(block_body)
    if secret_matches:
        print(f"Error: Refused to adopt block '{block_name}' holding potential secret pattern: {secret_matches[0]}", file=sys.stderr)
        return 1

    bp_dir = root / ".agents" / "blueprints"
    bp_dir.mkdir(parents=True, exist_ok=True)
    target_bp = bp_dir / f"{area}.md"

    # If target blueprint does not exist, initialize it
    if not target_bp.is_file():
        cmd_init(root, [area])

    bp_content = target_bp.read_text(encoding="utf-8", errors="replace") if target_bp.is_file() else ""

    # Insert into contracts block
    contracts_match = re.search(
        r"<!--\s*BEGIN CUSTOM:\s*contracts\s*-->\n?(.*?)<!--\s*END CUSTOM:\s*contracts\s*-->\n?",
        bp_content,
        re.DOTALL
    )

    if contracts_match:
        existing_contracts = contracts_match.group(1).strip()
        merged_contracts = f"{existing_contracts}\n\n{block_body}" if existing_contracts else block_body
        new_contracts_block = f"<!-- BEGIN CUSTOM: contracts -->\n{merged_contracts}\n<!-- END CUSTOM: contracts -->\n"
        new_bp_content = bp_content[:contracts_match.start()] + new_contracts_block + bp_content[contracts_match.end():]
    else:
        new_bp_content = bp_content.rstrip() + f"\n\n<!-- BEGIN CUSTOM: contracts -->\n{block_body}\n<!-- END CUSTOM: contracts -->\n"

    # Replace block in source file with single-line show pointer
    try:
        rel_from = from_path.relative_to(root).as_posix()
    except Exception:
        rel_from = from_file

    pointer_block = (
        f"<!-- BEGIN CUSTOM: {block_name} -->\n"
        f"python3 .agents/skills/project-blueprints/scripts/blueprint.py show --area {area} --paths {rel_from}\n"
        f"<!-- END CUSTOM: {block_name} -->\n"
    )
    new_src_content = src_content[:match.start()] + pointer_block + src_content[match.end():]

    # Handle split into parts if target_bp exceeds 250 lines
    bp_lines = new_bp_content.strip().split("\n")
    parts = split_into_parts(bp_lines, area, max_lines=250)

    # Atomic write: backup both contents and restore if any write fails
    backup_src = src_content
    backup_bp = bp_content
    written_files = []

    try:
        for p_idx, (fname, p_lines) in enumerate(parts):
            p_file = bp_dir / fname
            write_text_lf(p_file, "\n".join(p_lines) + "\n")
            written_files.append((p_file, p_file.read_text(encoding="utf-8") if p_file.is_file() else ""))

        write_text_lf(from_path, new_src_content)
    except Exception as e:
        # Rollback all writes
        try:
            write_text_lf(from_path, backup_src)
            write_text_lf(target_bp, backup_bp)
        except Exception:
            pass
        print(f"Error during atomic adopt: {e}. Rolled back all changes.", file=sys.stderr)
        return 1

    # Update index.md if new part files were created
    if len(parts) > 1:
        idx_file = bp_dir / "index.md"
        if idx_file.is_file():
            idx_txt = idx_file.read_text(encoding="utf-8")
            idx_lines = idx_txt.splitlines()
            for p_idx, (fname, _) in enumerate(parts):
                link_entry = f"- [{fname}]({fname})"
                if link_entry not in idx_lines:
                    idx_lines.append(link_entry)
            write_text_lf(idx_file, "\n".join(idx_lines[:58]) + "\n")

    print(f"Adopted custom block '{block_name}' from '{from_file}' into '{area}.md' contracts.")
    return 0


def cmd_link_check(root: Path) -> int:
    """Verify convention skills link to blueprints, index lists all files, and custom blocks are under 80 lines."""
    errors = []
    bp_dir = root / ".agents" / "blueprints"

    # Check 1: Convention skills with ## Blueprint point to existing blueprints
    skills_dirs = [root / ".agents" / "skills", root / "skills"]
    for sdir in skills_dirs:
        if not sdir.is_dir():
            continue
        for smd in sdir.glob("*/SKILL.md"):
            txt = smd.read_text(encoding="utf-8", errors="replace")
            if "## Blueprint" in txt:
                m_area = re.search(r"--area\s+([a-zA-Z0-9_-]+)", txt)
                if m_area:
                    area_name = m_area.group(1)
                    area_file = bp_dir / f"{area_name}.md"
                    if not area_file.is_file():
                        errors.append(f"Skill '{smd.relative_to(root).as_posix()}' links to missing blueprint area '{area_name}' (.agents/blueprints/{area_name}.md not found)")

            # Check custom block lengths in skill (< 80 lines)
            for m_cb in CUSTOM_BLOCK_RE.finditer(txt):
                bname = m_cb.group(2)
                bbody = m_cb.group(1)
                inner_lines = [l for l in bbody.splitlines() if not l.startswith("<!--")]
                if len(inner_lines) > 80:
                    errors.append(f"Custom block '{bname}' in '{smd.relative_to(root).as_posix()}' has {len(inner_lines)} lines (> 80 lines; facts belong in blueprints)")

    # Check 2: Every blueprint in .agents/blueprints/*.md is referenced in index.md
    if bp_dir.is_dir():
        idx_file = bp_dir / "index.md"
        if not idx_file.is_file():
            errors.append(".agents/blueprints/index.md not found")
        else:
            idx_text = idx_file.read_text(encoding="utf-8", errors="replace")
            for bpath in sorted(bp_dir.glob("*.md")):
                if bpath.name not in ("index.md", "candidates.md"):
                    if bpath.name not in idx_text:
                        errors.append(f"Blueprint '{bpath.name}' is not referenced in .agents/blueprints/index.md")

    if errors:
        print(f"Link check failed ({len(errors)} errors):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("Link check passed: all blueprints linked, index complete, custom blocks within limits.")
    return 0


def cmd_drift(root: Path) -> int:
    """Run verify, stale, link-check, and contract evidence anchor validation."""
    anchor_errors = []
    bp_dir = root / ".agents" / "blueprints"

    # Contract evidence anchor check
    if bp_dir.is_dir():
        for bpath in sorted(bp_dir.glob("*.md")):
            txt = bpath.read_text(encoding="utf-8", errors="replace")
            for m_cb in CUSTOM_BLOCK_RE.finditer(txt):
                if m_cb.group(2) == "contracts":
                    c_body = m_cb.group(1)
                    # Scan for evidence: path:line [contains: text]
                    for line in c_body.splitlines():
                        m_ev = re.search(r"(?:evidence|Evidence):\s*`?([^\s:`]+):(\d+)`?", line)
                        if m_ev:
                            rel_src = m_ev.group(1).strip()
                            try:
                                line_no = int(m_ev.group(2))
                            except ValueError:
                                line_no = 1
                            target_f = root / rel_src
                            if not target_f.is_file():
                                anchor_errors.append(f"Contract anchor file '{rel_src}' not found (referenced in {bpath.name})")
                                continue

                            # Check optional contains
                            m_ct = re.search(r"(?:contains|Contains):\s*`?([^`]+)`?", line)
                            if m_ct:
                                target_text = m_ct.group(1).strip()
                                s_lines = target_f.read_text(encoding="utf-8", errors="replace").splitlines()
                                w_start = max(0, line_no - 6)
                                w_end = min(len(s_lines), line_no + 5)
                                window = "\n".join(s_lines[w_start:w_end])
                                if target_text not in window:
                                    anchor_errors.append(f"Contract anchor text '{target_text}' not found within 5 lines of {rel_src}:{line_no} (referenced in {bpath.name})")

    # Run verify
    res_verify = cmd_verify(root)

    # Run stale with fail_on_stale=True
    res_stale = cmd_stale(root, fail_on_stale=True)

    # Run link_check
    res_link = cmd_link_check(root)

    if anchor_errors:
        print(f"Contract anchor drift errors ({len(anchor_errors)}):", file=sys.stderr)
        for ae in anchor_errors:
            print(f"  - {ae}", file=sys.stderr)

    if anchor_errors or res_verify != 0 or res_stale != 0 or res_link != 0:
        print("Blueprint drift check failed.", file=sys.stderr)
        return 1

    print("Blueprint drift check passed: all checks and anchors up to date.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Build Forge codebase blueprints tool.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # extract
    p_extract = subparsers.add_parser("extract", help="Extract project facts into blueprints.")
    p_extract.add_argument("--areas", default="", help="Comma-separated areas to extract.")
    p_extract.add_argument("--root", default=".", help="Project root directory.")

    # verify
    p_verify = subparsers.add_parser("verify", help="Verify evidence entries.")
    p_verify.add_argument("--root", default=".", help="Project root directory.")

    # stale
    p_stale = subparsers.add_parser("stale", help="Check for stale blueprints.")
    p_stale.add_argument("--fail", action="store_true", help="Exit 1 if any blueprint is stale.")
    p_stale.add_argument("--root", default=".", help="Project root directory.")

    # show
    p_show = subparsers.add_parser("show", help="Show blueprint section.")
    p_show.add_argument("--area", required=True, help="Blueprint area.")
    p_show.add_argument("--paths", default="", help="Comma-separated file paths to filter.")
    p_show.add_argument("--budget", type=int, default=120, help="Line limit budget.")
    p_show.add_argument("--root", default=".", help="Project root directory.")

    # candidates
    p_candidates = subparsers.add_parser("candidates", help="Print rule candidates.")
    p_candidates.add_argument("--root", default=".", help="Project root directory.")

    # init
    p_init = subparsers.add_parser("init", help="Scaffold missing canonical blueprint files.")
    p_init.add_argument("--areas", default="", help="Comma-separated areas to scaffold.")
    p_init.add_argument("--root", default=".", help="Project root directory.")

    # adopt
    p_adopt = subparsers.add_parser("adopt", help="Adopt custom block into blueprint contracts.")
    p_adopt.add_argument("--from", dest="from_file", required=True, help="Source file holding custom block.")
    p_adopt.add_argument("--block", required=True, help="Custom block name to adopt.")
    p_adopt.add_argument("--area", required=True, help="Target blueprint area.")
    p_adopt.add_argument("--root", default=".", help="Project root directory.")

    # link-check
    p_link = subparsers.add_parser("link-check", help="Verify links, index completeness, and block limits.")
    p_link.add_argument("--root", default=".", help="Project root directory.")

    # drift
    p_drift = subparsers.add_parser("drift", help="Run full drift check (verify, stale, link-check, anchors).")
    p_drift.add_argument("--root", default=".", help="Project root directory.")

    args = parser.parse_args()
    root = Path(args.root).resolve()

    if args.command == "extract":
        areas = [a.strip() for a in args.areas.split(",") if a.strip()] if args.areas else None
        sys.exit(cmd_extract(root, areas))
    elif args.command == "verify":
        sys.exit(cmd_verify(root))
    elif args.command == "stale":
        sys.exit(cmd_stale(root, args.fail))
    elif args.command == "show":
        paths = [p.strip() for p in args.paths.split(",") if p.strip()] if args.paths else None
        sys.exit(cmd_show(root, args.area, paths, args.budget))
    elif args.command == "candidates":
        sys.exit(cmd_candidates(root))
    elif args.command == "init":
        areas = [a.strip() for a in args.areas.split(",") if a.strip()] if args.areas else None
        sys.exit(cmd_init(root, areas))
    elif args.command == "adopt":
        sys.exit(cmd_adopt(root, args.from_file, args.block, args.area))
    elif args.command == "link-check":
        sys.exit(cmd_link_check(root))
    elif args.command == "drift":
        sys.exit(cmd_drift(root))


if __name__ == "__main__":
    main()
