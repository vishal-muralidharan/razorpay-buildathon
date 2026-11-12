#!/usr/bin/env python3
"""Suggest commit scopes for changed or staged files based on project profile globs.

Usage:
  python suggest_scope.py --profile PATH --files file1 [file2 ...]
  python suggest_scope.py --profile PATH --staged [--root REPO_ROOT]

Ranks scopes by glob matches, prints the top 3 with their purpose,
or prints the full list of available scopes when nothing matches.
Needs PyYAML (pip install pyyaml).
"""
import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")


def normalize_path(p: str) -> str:
    """Normalize file path for cross-platform glob matching."""
    norm = p.replace("\\", "/").strip()
    if norm.startswith("./"):
        norm = norm[2:]
    return norm


def parse_scopes(profile_data: dict) -> list:
    """Extract list of scope dicts: {name, purpose, paths}."""
    git = profile_data.get("git") or {}
    raw_scopes = git.get("scopes") or []
    scopes = []
    for s in raw_scopes:
        if isinstance(s, str):
            scopes.append({"name": s, "purpose": "", "paths": []})
        elif isinstance(s, dict):
            name = str(s.get("name", "")).strip()
            if name:
                scopes.append({
                    "name": name,
                    "purpose": str(s.get("purpose", "")).strip(),
                    "paths": [normalize_path(str(p)) for p in (s.get("paths") or []) if p],
                })
    return scopes


def match_file_against_patterns(filepath: str, patterns: list) -> bool:
    """Check if filepath matches any pattern glob."""
    for pat in patterns:
        if fnmatch.fnmatch(filepath, pat):
            return True
        # Allow matching nested paths when glob is a directory pattern or bare prefix
        if pat.endswith("/*") and fnmatch.fnmatch(filepath, pat + "*"):
            return True
        if not pat.endswith("*") and filepath.startswith(pat.rstrip("/") + "/"):
            return True
    return False


def get_staged_files(root: Path) -> list:
    """Retrieve list of staged files using git diff."""
    try:
        res = subprocess.run(
            ["git", "-C", str(root), "diff", "--name-only", "--cached"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0:
            return [normalize_path(line) for line in res.stdout.splitlines() if line.strip()]
    except Exception:
        pass
    return []


def suggest_scopes(scopes: list, files: list) -> tuple:
    """Rank scopes against files. Return (matched_list, full_list)."""
    norm_files = [normalize_path(f) for f in files if f]
    scored = []

    for scope in scopes:
        count = 0
        if norm_files and scope["paths"]:
            for f in norm_files:
                if match_file_against_patterns(f, scope["paths"]):
                    count += 1
        scored.append((count, scope["name"], scope))

    # Sort deterministically: highest count first, then alphabetical by name
    scored.sort(key=lambda item: (-item[0], item[1]))

    positive_matches = [item[2] for item in scored if item[0] > 0]
    all_alphabetical = sorted(scopes, key=lambda s: s["name"])

    return positive_matches, all_alphabetical



DEFAULT_PROFILE = ".agents/project-profile.yaml"


def resolve_profile_arg(profile, root=None) -> str:
    """Return the profile path. Defaults to .agents/project-profile.yaml under --root or the current folder."""
    if profile:
        return profile
    candidate = Path(root or ".") / DEFAULT_PROFILE
    if not candidate.is_file():
        sys.exit(f"ERROR: no profile at {candidate}. Pass --profile <path>.")
    return str(candidate)

def main():
    ap = argparse.ArgumentParser(description="Suggest commit scopes based on file paths.")
    ap.add_argument("--profile", default=None, help="Path to the profile. Defaults to .agents/project-profile.yaml under --root")
    ap.add_argument("--files", nargs="*", help="List of file paths to rank")
    ap.add_argument("--staged", action="store_true", help="Inspect git staged files")
    ap.add_argument("--root", default=".", help="Project repository root directory")
    a = ap.parse_args()
    a.profile = resolve_profile_arg(a.profile, a.root)

    prof_path = Path(a.profile).resolve()
    if not prof_path.is_file():
        sys.exit(f"ERROR: Profile not found at {prof_path}")

    try:
        prof = yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        sys.exit(f"ERROR: Cannot read profile: {e}")

    scopes = parse_scopes(prof)
    if not scopes:
        print("No commit scopes defined in git.scopes.")
        return

    root = Path(a.root).resolve()
    files = []
    if a.files is not None:
        files.extend(a.files)
    if a.staged:
        files.extend(get_staged_files(root))

    positive, all_scopes = suggest_scopes(scopes, files)

    if positive:
        print("Suggested scopes:")
        for sc in positive[:3]:
            desc = f" - {sc['purpose']}" if sc["purpose"] else ""
            print(f"  {sc['name']}{desc}")
    else:
        print("No specific scope matched. Available scopes:")
        for sc in all_scopes:
            desc = f" - {sc['purpose']}" if sc["purpose"] else ""
            print(f"  {sc['name']}{desc}")


if __name__ == "__main__":
    main()

