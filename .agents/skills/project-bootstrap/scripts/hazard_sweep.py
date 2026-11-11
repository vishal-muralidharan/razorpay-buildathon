#!/usr/bin/env python3
"""Run a hazard sweep across a repository to detect common code hazards.

Usage: python hazard_sweep.py [repo_root] [--json]

Inspects the repository files for candidate hazards based on the stack:
- native controls (native-controls pack)
- web hazards (web-hazards pack)
- raw colors (ui-no-raw-hex)
- hex in styles (style-no-raw-hex)
- any in TypeScript (ts-no-any, only when TypeScript is detected)
- storage outside storage layer (data-storage-layer-only, only when storage exists)

Reports violations with file:line evidence so the user can fix them or
record them as exceptions with reasons.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

IGNORE_DIRS = {
    "node_modules", "dist", "build", ".git", ".next", ".nuxt", "coverage",
    ".venv", "venv", "__pycache__", ".turbo", ".vercel", ".netlify", "target", "out"
}
MAX_BYTES = 1_000_000


def list_files(root: Path):
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for name in filenames:
            rel = Path(dirpath, name).relative_to(root).as_posix()
            files.append(rel)
    return sorted(files)


def scan_file_for_regex(root: Path, rel_path: str, rx: re.Pattern):
    violations = []
    full_path = root / rel_path
    try:
        if full_path.stat().st_size > MAX_BYTES:
            return violations
        text = full_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return violations

    for line_num, line in enumerate(text.splitlines(), 1):
        m = rx.search(line)
        if m:
            matched_str = m.group(0).strip()
            if len(matched_str) > 60:
                matched_str = matched_str[:57] + "..."
            violations.append({
                "file": rel_path,
                "line": line_num,
                "match": matched_str
            })
    return violations


def detect_stack_traits(root: Path, files: list):
    has_ts = any(f.endswith((".ts", ".tsx")) for f in files)
    has_web = any(f.endswith((".html", ".jsx", ".tsx", ".vue", ".svelte")) for f in files)
    if (root / "package.json").is_file():
        has_web = True

    has_styles = any(f.endswith((".css", ".scss", ".sass", ".less")) for f in files)

    has_storage = False
    storage_terms = ["localStorage", "sessionStorage", "indexedDB"]
    for f in files:
        if f.endswith((".js", ".jsx", ".ts", ".tsx")):
            fp = root / f
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
                if any(st in content for st in storage_terms):
                    has_storage = True
                    break
            except OSError:
                continue

    profile_path = root / ".agents" / "project-profile.yaml"
    if profile_path.is_file():
        try:
            prof = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
            if prof.get("data", {}).get("storage"):
                has_storage = True
        except Exception:
            pass

    return {
        "has_ts": has_ts,
        "has_web": has_web,
        "has_styles": has_styles,
        "has_storage": has_storage,
    }


def define_hazard_specs(traits: dict):
    specs = []

    # 1. Native controls
    specs.append({
        "id": "native-controls",
        "name": "Native controls (native-controls pack)",
        "applicable": traits["has_web"],
        "default": True,
        "description": "Prevent unstyled native pickers, selects, and browser dialogs.",
        "checks": [
            {
                "id": "ui-no-native-pickers",
                "pattern": r"(?<![\w-])type\s*=\s*(?:\{\s*)?[\"'](?:date|time|color|datetime-local|month|week)[\"']",
                "exts": (".jsx", ".tsx", ".html", ".vue", ".svelte"),
                "exclude_dirs": ["components/ui", "components/primitives"]
            },
            {
                "id": "ui-no-native-selects",
                "pattern": r"<select\b",
                "exts": (".jsx", ".tsx", ".html", ".vue", ".svelte"),
                "exclude_dirs": ["components/ui", "components/primitives"]
            },
            {
                "id": "ui-no-browser-dialogs",
                "pattern": r"(?<![\w.$])(?:window\.)?(?:alert|confirm|prompt)\s*\(",
                "exts": (".js", ".jsx", ".ts", ".tsx", ".html", ".vue", ".svelte"),
                "exclude_dirs": ["test", "tests"]
            }
        ]
    })

    # 2. Web hazards
    specs.append({
        "id": "web-hazards",
        "name": "Web hazards (web-hazards pack)",
        "applicable": traits["has_web"],
        "default": True,
        "description": "Block console logs, unvetted eval, raw innerHTML, and committed .env files.",
        "checks": [
            {
                "id": "web-no-console",
                "pattern": r"(?<![\w.$])console\.(?:log|debug)\s*\(",
                "exts": (".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".html"),
                "exclude_dirs": ["test", "tests", "__tests__"]
            },
            {
                "id": "web-target-blank-rel",
                "pattern": r"^(?!.*rel=[\"\x27][^\"\x27]*(?:noopener|noreferrer)).*target=[\"\x27]_blank[\"\x27]",
                "exts": (".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".html"),
                "exclude_dirs": []
            },
            {
                "id": "web-no-raw-eval",
                "pattern": r"(?<![\w$])(?:window\.)?eval\s*\(",
                "exts": (".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".html"),
                "exclude_dirs": []
            },
            {
                "id": "web-no-inner-html",
                "pattern": r"(?<![\w$])(?:innerHTML\s*=|dangerouslySetInnerHTML\b)",
                "exts": (".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".html"),
                "exclude_dirs": []
            }
        ],
        "file_checks": [
            {
                "id": "web-no-committed-env",
                "pattern": r"(?:^|/)\.env(?:\.local|\.[a-zA-Z0-9]+)?$",
                "exclude": [".env.example", ".env.template"]
            }
        ]
    })

    # 3. Raw colors
    specs.append({
        "id": "raw-colors",
        "name": "Raw colors (ui-no-raw-hex, ui-no-color-funcs)",
        "applicable": traits["has_web"] or traits["has_styles"],
        "default": True,
        "description": "Forbid raw hex colors and rgb/hsl function calls outside token files.",
        "checks": [
            {
                "id": "ui-no-raw-hex",
                "pattern": r"(?<![\w&/])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b",
                "exts": (".js", ".jsx", ".ts", ".tsx", ".css", ".html"),
                "exclude_dirs": ["tokens", "styles/tokens"]
            },
            {
                "id": "ui-no-color-funcs",
                "pattern": r"\b(?:rgb|rgba|hsl|hsla)\(",
                "exts": (".js", ".jsx", ".ts", ".tsx", ".css"),
                "exclude_dirs": ["tokens", "styles/tokens"]
            }
        ]
    })

    # 4. Hex in styles
    specs.append({
        "id": "hex-in-styles",
        "name": "Hex in styles (style-no-raw-hex)",
        "applicable": traits["has_styles"],
        "default": True,
        "description": "Forbid literal hex codes inside CSS and styling files.",
        "checks": [
            {
                "id": "style-no-raw-hex",
                "pattern": r"#[0-9a-fA-F]{3,8}\b",
                "exts": (".css", ".scss", ".sass", ".less"),
                "exclude_dirs": ["tokens"]
            }
        ]
    })

    # 5. Any in TypeScript
    specs.append({
        "id": "ts-no-any",
        "name": "Any in TypeScript (ts-no-any)",
        "applicable": traits["has_ts"],
        "default": True,
        "description": "Forbid bare any type annotations in TypeScript files.",
        "checks": [
            {
                "id": "ts-no-any",
                "pattern": r":\s*any\b",
                "exts": (".ts", ".tsx"),
                "exclude_dirs": ["test", "tests"]
            }
        ]
    })

    # 6. Storage outside storage layer
    specs.append({
        "id": "storage-layer-only",
        "name": "Storage outside storage layer (data-storage-layer-only)",
        "applicable": traits["has_storage"],
        "default": True,
        "description": "Enforce that browser storage calls go through a dedicated wrapper.",
        "checks": [
            {
                "id": "data-storage-layer-only",
                "pattern": r"\b(?:localStorage|sessionStorage|indexedDB)\b",
                "exts": (".js", ".jsx", ".ts", ".tsx"),
                "exclude_dirs": ["storage", "lib/storage", "test", "tests"]
            }
        ]
    })

    return specs


def run_sweep(root: Path):
    files = list_files(root)
    traits = detect_stack_traits(root, files)
    specs = define_hazard_specs(traits)

    results = []
    for s in specs:
        if not s["applicable"]:
            continue

        item_violations = []
        for chk in s.get("checks", []):
            rx = re.compile(chk["pattern"])
            target_exts = chk["exts"]
            ex_dirs = chk.get("exclude_dirs", [])

            for f in files:
                if not f.endswith(target_exts):
                    continue
                if any(f"/{ed}/" in f"/{f}/" or f.startswith(f"{ed}/") for ed in ex_dirs):
                    continue
                v_list = scan_file_for_regex(root, f, rx)
                for v in v_list:
                    v["rule_id"] = chk["id"]
                    item_violations.append(v)

        for fchk in s.get("file_checks", []):
            frx = re.compile(fchk["pattern"])
            f_excludes = fchk.get("exclude", [])
            for f in files:
                if any(f.endswith(fe) for fe in f_excludes):
                    continue
                if frx.search(f):
                    item_violations.append({
                        "file": f,
                        "line": 1,
                        "match": "Forbidden file committed",
                        "rule_id": fchk["id"]
                    })

        results.append({
            "id": s["id"],
            "name": s["name"],
            "default": s["default"],
            "description": s["description"],
            "violations_count": len(item_violations),
            "violations": item_violations
        })

    return results, traits


def main():
    ap = argparse.ArgumentParser(description="Sweep repository for common hazard patterns.")
    ap.add_argument("root", nargs="?", default=".", help="Target repository root path.")
    ap.add_argument("--json", action="store_true", help="Print findings as JSON.")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        sys.exit(f"Directory not found: {args.root}")

    results, traits = run_sweep(root)

    if args.json:
        payload = {
            "root": root.as_posix(),
            "traits": traits,
            "checklist": results
        }
        print(json.dumps(payload, indent=2))
        return

    print("Hazard Sweep Checklist:")
    for item in results:
        v_count = item["violations_count"]
        status = f"CLEAN (0 violations)" if v_count == 0 else f"FLAGGED ({v_count} violation(s))"
        print(f"  [x] {item['name']} [Default: yes] - {status}")
        if v_count > 0:
            for v in item["violations"][:5]:
                print(f"      {v['file']}:{v['line']}: {v['match']}")
            if v_count > 5:
                print(f"      ... and {v_count - 5} more")
            print("      Action: Ask user: fix now, or record as exceptions with reasons.")
        print()


if __name__ == "__main__":
    main()

