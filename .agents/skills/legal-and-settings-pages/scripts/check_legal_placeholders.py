#!/usr/bin/env python3
"""List every unresolved [TODO: ...] and [CONFIRM: ...] marker, grouped by file and section.

Usage: python check_legal_placeholders.py [--root .] [--config .agents/legal-config.yaml]
                                          [--include GLOB ...] [--strict]

Scans source files and docs for bracket markers, and the legal config for
values that start with TODO or CONFIRM. Exit 1 with --strict when any remain.
Needs PyYAML only when the config file exists (pip install pyyaml).
"""
import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

IGNORE_DIRS = {"node_modules", "dist", "build", ".git", ".next", ".nuxt", "coverage", ".venv",
               "venv", "__pycache__", ".turbo", ".vercel", ".netlify", "target", "out"}
EXT = {".jsx", ".tsx", ".js", ".ts", ".vue", ".svelte", ".html", ".md"}
MARKER = re.compile(r"\[(TODO|CONFIRM)\b[^\]]*\]")
HEADING = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>|^\s*#{1,6}\s+(.*)$")


def nearest_heading(lines, idx):
    for j in range(idx, -1, -1):
        m = HEADING.search(lines[j])
        if m:
            text = re.sub(r"<[^>]+>|\{[^}]*\}", "", m.group(1) or m.group(2) or "").strip()
            if text:
                return text
    return "(no heading above)"


def scan_files(root, include_ext):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for name in filenames:
            p = Path(dirpath, name)
            if p.suffix in include_ext and "test" not in name.lower():
                yield p


def walk_config(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk_config(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_config(v, f"{path}[{i}]")
    elif isinstance(node, str) and re.match(r"^\s*(TODO|CONFIRM)\b", node):
        yield path, node


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default=".agents/legal-config.yaml")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    root = Path(a.root).resolve()

    found = defaultdict(list)
    for p in scan_files(root, EXT):
        try:
            lines = p.read_text(errors="ignore").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines):
            for m in MARKER.finditer(line):
                found[p.relative_to(root).as_posix()].append((nearest_heading(lines, i), m.group(0)))

    cfg = root / a.config
    if cfg.exists():
        try:
            import yaml
            data = yaml.safe_load(cfg.read_text()) or {}
            for path, value in walk_config(data):
                found[a.config].append((path, value))
        except ImportError:
            print("NOTE  PyYAML missing, config file not checked")

    total = 0
    for f in sorted(found):
        print(f"\n{f}")
        for section, marker in found[f]:
            total += 1
            print(f"  [{section}] {marker}")
    print(f"\n{total} unresolved marker(s) in {len(found)} file(s)")
    sys.exit(1 if (a.strict and total) else 0)


if __name__ == "__main__":
    main()
