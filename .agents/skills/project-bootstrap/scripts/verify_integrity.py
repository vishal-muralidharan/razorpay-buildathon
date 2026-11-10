#!/usr/bin/env python3
"""Offline integrity verification for Build Forge pipeline skills.

Verifies installed skills against .agents/build-forge.lock.json using SHA256 hashes.
Exits 0 if all skills match, 1 if any skill is modified, missing, or has extra files,
and 2 if the lock file is missing or invalid.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


def hash_file(file_path: Path) -> str:
    try:
        content = file_path.read_text(encoding="utf-8")
        normalized = content.replace("\r\n", "\n")
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    except UnicodeDecodeError:
        return hashlib.sha256(file_path.read_bytes()).hexdigest()


def compute_skills_manifest(skills_dir: Path, allowed_skills: set = None) -> dict:
    manifest = {}
    if not skills_dir.is_dir():
        return manifest
    for skill_path in skills_dir.iterdir():
        if not skill_path.is_dir() or skill_path.name == "__pycache__":
            continue
        if allowed_skills and skill_path.name not in allowed_skills:
            continue
        for root, dirs, files in os.walk(skill_path):
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")
            dirs.sort()
            for f in sorted(files):
                if f.endswith(".pyc") or f == ".DS_Store":
                    continue
                full_path = Path(root) / f
                rel_path = "skills/" + str(full_path.relative_to(skills_dir)).replace("\\", "/")
                manifest[rel_path] = hash_file(full_path)
    return manifest


def verify(root_dir: Path, lock_path: Path = None, target_version: str = None) -> int:
    if lock_path is None:
        lock_path = root_dir / ".agents" / "build-forge.lock.json"

    if not lock_path.is_file():
        print(f"Verify error: Lock file not found at {lock_path}", file=sys.stderr)
        return 2

    try:
        lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Verify error: Invalid JSON in {lock_path}: {e}", file=sys.stderr)
        return 1

    if target_version:
        installed_version = lock_data.get("_version") or lock_data.get("version")
        if installed_version and installed_version != target_version:
            print(f"Verify error: Installed version '{installed_version}' does not match pinned version '{target_version}'", file=sys.stderr)
            return 1

    skills_dir = root_dir / ".agents" / "skills"
    installed_skills = set(lock_data["_installed"]) if isinstance(lock_data.get("_installed"), list) else None
    if installed_skills is None:
        lock_skills = {
            k.split("/")[1]
            for k in lock_data
            if k.startswith("skills/") and "/" in k[7:]
        }
        if skills_dir.is_dir():
            installed_skills = {
                d.name for d in skills_dir.iterdir()
                if d.is_dir() and d.name != "__pycache__" and d.name in lock_skills
            }
        else:
            installed_skills = set()

    current_manifest = compute_skills_manifest(skills_dir, installed_skills)
    failed = False

    for rel_file, expected_hash in lock_data.items():
        if rel_file.startswith("_") or rel_file == "version":
            continue
        parts = rel_file.split("/")
        if len(parts) >= 2 and parts[0] == "skills":
            skill_name = parts[1]
            if skill_name not in installed_skills:
                continue
        current_hash = current_manifest.get(rel_file)
        if not current_hash:
            print(f"  missing   .agents/{rel_file}", file=sys.stderr)
            failed = True
        elif current_hash != expected_hash:
            print(f"  modified  .agents/{rel_file}", file=sys.stderr)
            failed = True

    for rel_file in current_manifest:
        if rel_file.startswith("_") or rel_file == "version":
            continue
        if rel_file not in lock_data:
            print(f"  extra     .agents/{rel_file}", file=sys.stderr)
            failed = True

    if failed:
        return 1

    print("Verify ok: All skills match lock file.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Verify integrity of installed Build Forge skills.")
    parser.add_argument("--root", default=".", help="Root directory of the project (default: .)")
    parser.add_argument("--lock", default=None, help="Path to lock file (default: <root>/.agents/build-forge.lock.json)")
    parser.add_argument("--version", dest="target_version", default=None, help="Pinned target version to verify against")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    lock = Path(args.lock).resolve() if args.lock else None
    sys.exit(verify(root, lock, args.target_version))


if __name__ == "__main__":
    main()
