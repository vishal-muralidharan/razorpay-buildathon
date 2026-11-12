#!/usr/bin/env python3
"""Check preservation of non-generated content across migration, rollout, or update.

Computes removed non-generated lines between BASE and HEAD for generated
convention skills and AGENTS.md (git diff -U0), trims and collapses whitespace,
ignores lines shorter than 12 characters and lines that are only markdown fences,
table separators or comment markers, then searches the HEAD tree in:
  - the same files
  - .agents/blueprints/**
  - .agents/notes/**
  - .agents/legacy-skills/**
  - .agents/custom-orphans.md
  - AGENTS.generated.md

Prints the count of missing lines and the first 20, and exits 1 if any is missing.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

CONVENTION_SKILLS = {
    "build-ui",
    "maintain-design-system",
    "review-responsive-design",
    "review-directory-structure",
    "file-folder-naming",
    "review-db-structure",
}

HUMAN_REVIEW_MESSAGE = (
    "Table rows or facts replaced by generated tables are reported "
    "as missing so a human can review and decide."
)


def run_git(root: Path, args: list) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        ["git", "-C", str(root)] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def is_ignored_line(text: str) -> bool:
    s = collapse_ws(text)
    if len(s) < 12:
        return True
    if re.match(r"^(`{3,}|~{3,})", s):
        return True
    if re.match(r"^\|?[\s\-:|]+\|?$", s):
        return True
    if s.startswith("<!--") and s.endswith("-->"):
        return True
    return False


def get_custom_block_line_ranges(content: str) -> list:
    lines = content.splitlines()
    ranges = []
    in_custom = False
    start = None
    for i, line in enumerate(lines, 1):
        if "<!-- BEGIN CUSTOM:" in line:
            in_custom = True
            start = i
        elif "<!-- END CUSTOM:" in line:
            if in_custom and start is not None:
                ranges.append((start, i))
            in_custom = False
            start = None
    return ranges


def get_tree_files(root: Path, ref: str) -> list:
    res = run_git(root, ["ls-tree", "-r", "--name-only", ref])
    if res.returncode != 0:
        return []
    return [line.strip().replace("\\", "/") for line in res.stdout.splitlines() if line.strip()]


def read_git_file(root: Path, ref: str, path: str) -> str:
    res = run_git(root, ["show", f"{ref}:{path}"])
    if res.returncode != 0:
        return ""
    return res.stdout.replace("\r\n", "\n")


def default_paths(root: Path, base: str, head: str) -> list:
    candidates = {"AGENTS.md"}
    for skill in CONVENTION_SKILLS:
        candidates.add(f".agents/skills/{skill}/SKILL.md")
        candidates.add(f"skills/{skill}/SKILL.md")

    base_files = set(get_tree_files(root, base))
    head_files = set(get_tree_files(root, head))
    all_files = base_files | head_files

    matched = sorted([c for c in candidates if c in all_files])
    if not matched:
        matched = ["AGENTS.md"]
        for skill in sorted(CONVENTION_SKILLS):
            matched.append(f".agents/skills/{skill}/SKILL.md")
    return matched


def find_removed_non_generated_lines(root: Path, base: str, head: str, paths: list) -> list:
    removed_items = []
    for path in paths:
        base_content = read_git_file(root, base, path)
        if not base_content:
            continue

        is_stamped = ("<!-- build-forge:generated" in base_content) or (
            "<!-- Generated from" in base_content
        )
        custom_ranges = get_custom_block_line_ranges(base_content) if is_stamped else []

        res = run_git(root, ["diff", "-U0", base, head, "--", path])
        if res.returncode != 0 or not res.stdout:
            continue

        base_line_no = 0
        in_hunk = False
        for raw_line in res.stdout.splitlines():
            if raw_line.startswith("@@ "):
                m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", raw_line)
                if m:
                    base_line_no = int(m.group(1))
                    in_hunk = True
                continue
            if not in_hunk:
                continue
            if raw_line.startswith("--- ") or raw_line.startswith("+++ "):
                continue
            if raw_line.startswith("-"):
                line_content = raw_line[1:]
                current_line_no = base_line_no
                base_line_no += 1

                if is_stamped:
                    in_custom = any(start <= current_line_no <= end for start, end in custom_ranges)
                    if not in_custom:
                        continue

                if is_ignored_line(line_content):
                    continue

                collapsed = collapse_ws(line_content)
                removed_items.append({"path": path, "line_no": current_line_no, "text": collapsed})
            elif raw_line.startswith(" "):
                base_line_no += 1

    return removed_items


def collect_head_search_targets(root: Path, head: str, checked_paths: list) -> dict:
    head_files = get_tree_files(root, head)
    targets = {}
    checked_set = set(checked_paths)

    for p in head_files:
        norm = p.replace("\\", "/")
        match = (
            norm in checked_set
            or norm.startswith(".agents/blueprints/")
            or norm.startswith(".agents/notes/")
            or norm.startswith(".agents/legacy-skills/")
            or norm == ".agents/custom-orphans.md"
            or norm == "AGENTS.generated.md"
        )
        if match:
            content = read_git_file(root, head, norm)
            targets[norm] = content
    return targets


def check_preservation(root: Path, base: str, head: str, paths: list = None) -> dict:
    if paths is None or len(paths) == 0:
        paths = default_paths(root, base, head)

    removed = find_removed_non_generated_lines(root, base, head, paths)
    if not removed:
        return {
            "status": "OK",
            "missing_count": 0,
            "missing": [],
            "first_20": [],
            "message": "All non-generated lines preserved.",
        }

    head_targets = collect_head_search_targets(root, head, paths)

    head_lines_set = set()
    head_collapsed_texts = []
    for _path, content in head_targets.items():
        for line in content.splitlines():
            line_c = collapse_ws(line)
            if line_c:
                head_lines_set.add(line_c)
        head_collapsed_texts.append(collapse_ws(content))

    missing = []
    seen = set()
    for item in removed:
        t = item["text"]
        if t in seen:
            continue
        in_lines = t in head_lines_set
        in_texts = any(t in blob for blob in head_collapsed_texts) if not in_lines else True
        if not (in_lines or in_texts):
            seen.add(t)
            missing.append(t)

    if missing:
        return {
            "status": "FAIL",
            "missing_count": len(missing),
            "missing": missing,
            "first_20": missing[:20],
            "message": HUMAN_REVIEW_MESSAGE,
        }

    return {
        "status": "OK",
        "missing_count": 0,
        "missing": [],
        "first_20": [],
        "message": "All non-generated lines preserved.",
    }


def main():
    ap = argparse.ArgumentParser(
        description="Check preservation of non-generated content across migration or update."
    )
    ap.add_argument("--root", default=".", help="Repository root directory")
    ap.add_argument("--base", required=True, help="Base git commit, branch, or ref")
    ap.add_argument("--head", default="HEAD", help="Head git commit, branch, or ref")
    ap.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="Paths to check (default: convention skills and AGENTS.md)",
    )
    ap.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = ap.parse_args()
    root = Path(args.root).resolve()

    res = check_preservation(root, args.base, args.head, args.paths)

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if res["status"] == "FAIL":
            print(f"Preservation check failed: {res['missing_count']} line(s) missing.")
            print("First 20 missing lines:")
            for line in res["first_20"]:
                print(f"  - {line}")
            print()
            print(res["message"])
        else:
            print("Preservation check passed: all non-generated lines preserved.")

    sys.exit(1 if res["status"] == "FAIL" else 0)


if __name__ == "__main__":
    main()

