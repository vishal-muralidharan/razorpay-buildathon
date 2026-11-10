#!/usr/bin/env python3
"""Add a single `check` script to package.json that chains lint, test and build.

Usage: python ensure_check_script.py --root REPO_ROOT [--profile PATH] [--pm npm] [--force] [--dry-run]

Only scripts that exist are chained. The order is lint, test, build.
An existing `check` script is kept unless --force is set.
The package manager comes from --pm, then from the profile's
stack.package_manager, then from npm.
"""
import argparse
import json
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--pm", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    pkg_path = Path(a.root) / "package.json"
    if not pkg_path.exists():
        sys.exit("No package.json found. Create the equivalent chain by hand for this stack.")
    pkg = json.loads(pkg_path.read_text())
    scripts = pkg.setdefault("scripts", {})

    pm = a.pm
    if not pm and a.profile:
        try:
            import yaml
            prof = yaml.safe_load(Path(a.profile).read_text()) or {}
            pm = (prof.get("stack") or {}).get("package_manager")
        except Exception:
            pm = None
    pm = pm if pm in ("npm", "pnpm", "yarn", "bun") else "npm"

    if "check" in scripts and not a.force:
        print(f"KEPT    scripts.check already exists: {scripts['check']}")
        return

    chain = [f"{pm} run {name}" for name in ("lint", "test", "build") if name in scripts]
    if not chain:
        sys.exit("None of lint, test or build exist in package.json scripts. Add them first.")
    missing = [n for n in ("lint", "test", "build") if n not in scripts]
    command = " && ".join(chain)

    if a.dry_run:
        print(f"DRY RUN would set scripts.check = {command}")
    else:
        scripts["check"] = command
        pkg_path.write_text(json.dumps(pkg, indent=2) + "\n")
        print(f"WROTE   scripts.check = {command}")
    if missing:
        print(f"NOTE    not chained because the script is missing: {', '.join(missing)}")


if __name__ == "__main__":
    main()
