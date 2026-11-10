#!/usr/bin/env python3
"""Profile schema migration framework for Build Forge.

Upgrades .agents/project-profile.yaml across schema versions through a registry
of sequential migrations keyed by schema_version.

Commands:
  plan [--profile PATH] [--root .]
  apply [--profile PATH] [--root .] [--apply]

Rules:
- Never deletes any rule or field added by the user.
- Unknown and custom fields are preserved intact.
- Writes files only when --apply is explicitly set.
- Creates no backup files because git tracks changes.
"""
import argparse
import difflib
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

SUPPORTED_SCHEMA_VERSIONS = (1, 2)


def migrate_v1_to_v2(profile: dict, root: Path) -> dict:
    """Migrate profile from schema_version 1 to 2.

    Preserves every rule and field added by the user. Unknown fields stay.
    Adds standard optional structure for blueprints and lifecycle configuration.
    """
    updated = dict(profile)
    updated["schema_version"] = 2

    # Standardize optional blueprints section if not present
    if "blueprints" not in updated:
        updated["blueprints"] = {
            "enabled": True,
            "dir": ".agents/blueprints"
        }

    return updated


# Registry of migration functions keyed by source schema_version.
# To add a migration, define migrate_vX_to_vY and register it here.
MIGRATIONS = {
    1: migrate_v1_to_v2,
}


def load_profile(profile_path: Path) -> tuple:
    if not profile_path.is_file():
        sys.exit(f"Error: profile not found at {profile_path}")
    try:
        raw_text = profile_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw_text)
    except Exception as e:
        sys.exit(f"Error reading profile {profile_path}: {e}")
    if not isinstance(data, dict):
        sys.exit("Error: profile must be a YAML mapping")
    return data, raw_text


def run_migrations(profile: dict, root: Path) -> tuple:
    cur_ver = profile.get("schema_version", 1)
    if not isinstance(cur_ver, int):
        sys.exit(f"Error: invalid schema_version: {cur_ver}")

    migrated = dict(profile)
    applied = []

    while cur_ver in MIGRATIONS:
        fn = MIGRATIONS[cur_ver]
        next_ver = cur_ver + 1
        migrated = fn(migrated, root)
        cur_ver = migrated.get("schema_version")
        if cur_ver not in SUPPORTED_SCHEMA_VERSIONS:
            sys.exit(f"Error: Migration produced unsupported schema_version {cur_ver}. Must be in {SUPPORTED_SCHEMA_VERSIONS}.")
        applied.append((cur_ver - 1, cur_ver))

    return migrated, applied


def format_diff(orig_text: str, new_text: str, from_label: str, to_label: str) -> str:
    orig_lines = orig_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = difflib.unified_diff(orig_lines, new_lines, fromfile=from_label, tofile=to_label)
    return "".join(diff)


def migrate_text_v1_to_v2(raw_text: str) -> str:
    lines = raw_text.splitlines(keepends=True)
    new_lines = []
    has_schema_version = False
    has_blueprints = False

    for line in lines:
        stripped = line.strip()
        if re.match(r"^schema_version:\s*1\b", stripped):
            new_line = re.sub(r"^(schema_version:\s*)1\b", r"\g<1>2", line)
            new_lines.append(new_line)
            has_schema_version = True
        else:
            if re.match(r"^blueprints:\s*", stripped):
                has_blueprints = True
            new_lines.append(line)

    if not has_schema_version and not any(re.match(r"^schema_version:\s*", l.strip()) for l in lines):
        new_lines.insert(0, "schema_version: 2\n")

    result = "".join(new_lines)
    if not has_blueprints:
        if not result.endswith("\n"):
            result += "\n"
        result += "\nblueprints: {}\n"

    return result


def cmd_plan(profile_path: Path, root: Path) -> bool:
    data, raw_text = load_profile(profile_path)
    orig_ver = data.get("schema_version", 1)

    if orig_ver == 1:
        new_text = migrate_text_v1_to_v2(raw_text)
        target_ver = 2
        print(f"Migration plan: schema_version {orig_ver} -> {target_ver} (1 step(s))\n")
        diff_output = format_diff(
            raw_text,
            new_text,
            f"{profile_path.name} (schema_version {orig_ver})",
            f"{profile_path.name} (schema_version {target_ver})"
        )
        if diff_output:
            print(diff_output)
        else:
            print("No textual changes generated.")
        return True

    print(f"Profile is up to date (schema_version {orig_ver}). No migrations needed.")
    return False


def cmd_apply(profile_path: Path, root: Path, do_apply: bool):
    data, raw_text = load_profile(profile_path)
    orig_ver = data.get("schema_version", 1)

    if orig_ver != 1:
        print(f"Profile is up to date (schema_version {orig_ver}). No migrations needed.")
        return

    if not do_apply:
        cmd_plan(profile_path, root)
        print("\nNotice: Dry-run only. No files were modified.")
        print(f"To apply this migration, run: python3 {Path(__file__).as_posix()} apply --apply")
        return

    new_text = migrate_text_v1_to_v2(raw_text)
    profile_path.write_text(new_text, encoding="utf-8")
    print(f"Successfully migrated {profile_path.name}: schema_version {orig_ver} -> 2.")


def main():
    ap = argparse.ArgumentParser(description="Profile schema migration framework.")
    sub = ap.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="Print the migration plan diff without modifying files.")
    p_plan.add_argument("--profile", default=None, help="Path to project profile YAML.")
    p_plan.add_argument("--root", default=".", help="Project root directory.")

    p_apply = sub.add_parser("apply", help="Apply migrations to profile.")
    p_apply.add_argument("--profile", default=None, help="Path to project profile YAML.")
    p_apply.add_argument("--root", default=".", help="Project root directory.")
    p_apply.add_argument("--apply", action="store_true", help="Write changes to profile file.")

    args = ap.parse_args()
    root = Path(args.root).resolve()
    prof_path = Path(args.profile).resolve() if args.profile else root / ".agents" / "project-profile.yaml"

    if args.command == "plan":
        cmd_plan(prof_path, root)
    elif args.command == "apply":
        cmd_apply(prof_path, root, args.apply)


if __name__ == "__main__":
    main()
