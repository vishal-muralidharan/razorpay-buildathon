#!/usr/bin/env python3
"""Detect facts about a repository and print them as JSON.

Usage: python detect_stack.py [repo_root]

Agent folders (.agents, .claude, .cursor and similar) are skipped when the
script counts source files, naming, tokens and storage hints, so that the
Build Forge skills installed in the project are never read as project code.

Read-only. Never writes to the repo. The output feeds the draft of
.agents/project-profile.yaml. Every value is a fact found in a file,
not a guess. Unknown stays empty.
"""
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

IGNORE = {"node_modules", "dist", "build", ".git", ".next", ".nuxt", "coverage",
          ".venv", "venv", "__pycache__", ".turbo", ".vercel", ".netlify", "target", "out"}
# Agent and tool folders hold installed skills and pointer files, not project code.
AGENT_DIRS = {".agents", ".claude", ".cursor", ".windsurf", ".gemini", ".codex", ".github"}
SRC_EXT = {".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".py", ".rs", ".go", ".dart", ".swift", ".kt"}

FRAMEWORKS = [("next", "Next.js"), ("nuxt", "Nuxt"), ("@remix-run/react", "Remix"), ("astro", "Astro"),
              ("@sveltejs/kit", "SvelteKit"), ("svelte", "Svelte"), ("vue", "Vue"), ("react", "React"),
              ("solid-js", "Solid"), ("@angular/core", "Angular"), ("expo", "Expo"),
              ("react-native", "React Native"), ("electron", "Electron"), ("hono", "Hono"),
              ("fastify", "Fastify"), ("express", "Express")]
BUNDLERS = [("vite", "Vite"), ("webpack", "Webpack"), ("rollup", "Rollup"), ("parcel", "Parcel"), ("esbuild", "esbuild")]
STYLING = [("tailwindcss", "Tailwind"), ("styled-components", "styled-components"), ("@emotion/react", "Emotion"),
           ("sass", "Sass")]
ROUTERS = [("react-router", "React Router"), ("react-router-dom", "React Router"),
           ("@tanstack/react-router", "TanStack Router"), ("vue-router", "Vue Router")]
STATE = [("@reduxjs/toolkit", "Redux Toolkit"), ("redux", "Redux"), ("zustand", "Zustand"),
         ("jotai", "Jotai"), ("mobx", "MobX"), ("pinia", "Pinia")]
TESTS = [("vitest", "Vitest"), ("jest", "Jest"), ("mocha", "Mocha"), ("@playwright/test", "Playwright"), ("cypress", "Cypress")]
LINTERS = [("oxlint", "Oxlint"), ("eslint", "ESLint"), ("@biomejs/biome", "Biome")]
SERVICES = [("@supabase/supabase-js", "Supabase"), ("firebase", "Firebase"), ("firebase-admin", "Firebase Admin"),
            ("@prisma/client", "Prisma"), ("drizzle-orm", "Drizzle"), ("mongoose", "Mongoose"), ("pg", "Postgres client")]
HOSTING_FILES = {"vercel.json": "Vercel", ".vercel": "Vercel", "netlify.toml": "Netlify",
                 "wrangler.toml": "Cloudflare", "wrangler.jsonc": "Cloudflare", "fly.toml": "Fly.io",
                 "render.yaml": "Render", "Dockerfile": "Docker"}
LOCKFILES = {"pnpm-lock.yaml": "pnpm", "yarn.lock": "yarn", "bun.lockb": "bun", "bun.lock": "bun",
             "package-lock.json": "npm", "poetry.lock": "poetry", "uv.lock": "uv", "Cargo.lock": "cargo"}
MANIFESTS = {"package.json": "javascript", "pyproject.toml": "python", "requirements.txt": "python",
             "Cargo.toml": "rust", "go.mod": "go", "pubspec.yaml": "dart", "Package.swift": "swift"}


def first(deps, table):
    for key, label in table:
        if key in deps:
            return label
    return ""


def walk(root, max_depth=4):
    out = []
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if any(part in IGNORE for part in rel.parts) or len(rel.parts) > max_depth + 1:
            continue
        if rel.parts and rel.parts[0] in AGENT_DIRS:
            continue
        out.append(p)
    return out


def case_of(stem):
    stem = stem.split(".")[0]
    if re.fullmatch(r"[A-Z][A-Za-z0-9]*", stem) and any(c.islower() for c in stem):
        return "PascalCase"
    if re.fullmatch(r"[a-z][a-z0-9]*([A-Z][a-z0-9]*)+", stem):
        return "camelCase"
    if re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)+", stem):
        return "kebab-case"
    if re.fullmatch(r"[a-z0-9]+(_[a-z0-9]+)+", stem):
        return "snake_case"
    if re.fullmatch(r"[a-z0-9]+", stem):
        return "lowercase"
    return "other"


def git_facts(root):
    if not (root / ".git").exists():
        return {"is_repo": False}
    try:
        subjects = subprocess.run(["git", "-C", str(root), "log", "-n", "100", "--pretty=%s"],
                                  capture_output=True, text=True, timeout=20).stdout.splitlines()
        bodies = subprocess.run(["git", "-C", str(root), "log", "-n", "100", "--pretty=%b%x00"],
                                capture_output=True, text=True, timeout=20).stdout.split("\x00")
    except Exception:
        return {"is_repo": True, "commits_sampled": 0}
    conv = re.compile(r"^(\w+)(?:\(([^)]+)\))?!?: .+")
    types, scopes, matched = Counter(), Counter(), 0
    for s in subjects:
        m = conv.match(s)
        if m:
            matched += 1
            types[m.group(1)] += 1
            if m.group(2):
                scopes[m.group(2)] += 1
    n = len(subjects)
    with_body = sum(1 for b in bodies if b.strip())
    default_branch = ""
    try:
        res_sym = subprocess.run(["git", "-C", str(root), "symbolic-ref", "refs/remotes/origin/HEAD"],
                                 capture_output=True, text=True, timeout=5)
        if res_sym.returncode == 0:
            default_branch = res_sym.stdout.strip().split("/")[-1]
    except Exception:
        pass
    if not default_branch:
        for candidate in ["main", "master"]:
            try:
                res_cand = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", f"refs/heads/{candidate}"],
                                          capture_output=True, text=True, timeout=5)
                if res_cand.returncode == 0:
                    default_branch = candidate
                    break
            except Exception:
                pass
    if not default_branch:
        try:
            res_curr = subprocess.run(["git", "-C", str(root), "branch", "--show-current"],
                                      capture_output=True, text=True, timeout=5)
            if res_curr.returncode == 0 and res_curr.stdout.strip():
                default_branch = res_curr.stdout.strip()
        except Exception:
            pass

    return {"is_repo": True, "commits_sampled": n,
            "default_branch": default_branch,
            "conventional_ratio": round(matched / n, 2) if n else 0,
            "types": dict(types.most_common(10)), "scopes": dict(scopes.most_common(15)),
            "commits_with_body_ratio": round(with_body / n, 2) if n else 0}


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not root.is_dir():
        sys.exit(f"Not a directory: {root}")
    facts = {"root": str(root), "evidence": {}}
    ev = facts["evidence"]

    top = sorted(p.name for p in root.iterdir() if p.name not in IGNORE and p.name != ".git")
    facts["root_entries"] = top

    manifests = [m for m in MANIFESTS if (root / m).exists()]
    facts["manifests"] = manifests
    langs = [MANIFESTS[m] for m in manifests]
    pkg, deps, scripts = {}, {}, {}
    if (root / "package.json").exists():
        try:
            pkg = json.loads((root / "package.json").read_text())
        except Exception:
            pkg = {}
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        scripts = pkg.get("scripts", {})
        ev["package_json"] = "package.json"
    ts = (root / "tsconfig.json").exists() or "typescript" in deps
    facts["language"] = "typescript" if ts else (langs[0] if langs else "")
    facts["name"] = pkg.get("name", root.name)
    facts["framework"] = first(deps, FRAMEWORKS)
    facts["bundler"] = first(deps, BUNDLERS)
    facts["styling"] = first(deps, STYLING)
    facts["router"] = first(deps, ROUTERS)
    facts["state"] = first(deps, STATE)
    facts["test_runner"] = first(deps, TESTS)
    facts["linter"] = first(deps, LINTERS)
    facts["services"] = [label for key, label in SERVICES if key in deps]
    facts["hosting"] = sorted({label for f, label in HOSTING_FILES.items() if (root / f).exists()})
    facts["package_manager"] = next((v for k, v in LOCKFILES.items() if (root / k).exists()), "")
    pm = facts["package_manager"] or "npm"
    run = "npm run" if pm == "npm" else f"{pm} run"
    facts["scripts"] = scripts
    facts["commands_suggested"] = {k: f"{run} {k}" for k in ("dev", "lint", "test", "build", "check", "deploy") if k in scripts}

    files = walk(root)
    src_files = [p for p in files if p.is_file() and p.suffix in SRC_EXT]
    facts["source_file_count"] = len(src_files)

    srcdir = next((root / d for d in ("src", "app", "lib") if (root / d).is_dir()), None)
    layers = []
    if srcdir:
        for d in [srcdir] + sorted(p for p in srcdir.rglob("*") if p.is_dir()):
            rel = d.relative_to(root)
            if any(part in IGNORE for part in rel.parts) or len(rel.parts) > 3:
                continue
            direct = [f.name for f in d.iterdir() if f.is_file()]
            if direct:
                layers.append({"path": rel.as_posix(), "files": len(direct), "sample": sorted(direct)[:4]})
    facts["layers"] = layers

    naming = {}
    for p in src_files:
        stem = p.name
        is_test = bool(re.search(r"\.(test|spec)\.", stem))
        kind = "test" if is_test else p.suffix.lstrip(".")
        naming.setdefault(kind, Counter())[case_of(stem.replace(".test", "").replace(".spec", ""))] += 1
    facts["naming_by_extension"] = {k: dict(v.most_common()) for k, v in naming.items()}
    test_files = [p for p in files if p.is_file() and re.search(r"\.(test|spec)\.", p.name)]
    facts["test_file_count"] = len(test_files)
    in_tests_dir = sum(1 for p in test_files if any(x in ("tests", "__tests__", "test") for x in p.relative_to(root).parts[:-1]))
    facts["tests_layout"] = ("none" if not test_files else "tests-dir" if in_tests_dir > len(test_files) / 2 else "colocated")

    tokens = []
    for p in files:
        if p.is_file() and p.suffix == ".css" and p.stat().st_size < 500_000:
            text = p.read_text(errors="ignore")
            if ":root" in text:
                tokens.append({"file": p.relative_to(root).as_posix(),
                               "css_variables": len(re.findall(r"--[\w-]+\s*:", text)),
                               "hex_values": len(re.findall(r"#[0-9a-fA-F]{3,8}\b", text))})
    facts["token_file_candidates"] = sorted(tokens, key=lambda t: -t["css_variables"])[:5]
    facts["rule_test_candidates"] = [p.relative_to(root).as_posix() for p in test_files if "rule" in p.name.lower()][:5]

    hints = Counter()
    for p in src_files[:2000]:
        if p.stat().st_size > 200_000:
            continue
        text = p.read_text(errors="ignore")
        for token in ("localStorage", "indexedDB", "supabase", "firebase", "collection(", "fetch("):
            if token in text:
                hints[token] += 1
    facts["storage_hints"] = dict(hints)

    facts["git"] = git_facts(root)

    # Scope candidates from git history and layers
    scope_candidates = []
    seen_scope_names = set()

    git_scopes = facts.get("git", {}).get("scopes", {})
    for sname in git_scopes:
        kname = re.sub(r"[^a-z0-9]+", "-", str(sname).lower()).strip("-")
        if not kname or kname in seen_scope_names:
            continue
        matched_paths = []
        for pat in [f"{kname}/**", f"src/{kname}/**", f"app/{kname}/**", f"packages/{kname}/**"]:
            norm = pat.replace("/**", "")
            target_dir = root / norm
            if target_dir.is_dir() and any(p.is_file() for p in target_dir.rglob("*")):
                matched_paths.append(pat)
                break
        if matched_paths:
            scope_candidates.append({
                "name": kname,
                "paths": matched_paths
            })
            seen_scope_names.add(kname)

    for l in layers:
        lpath = l["path"]
        last_seg = lpath.split("/")[-1]
        kname = re.sub(r"[^a-z0-9]+", "-", last_seg.lower()).strip("-")
        if not kname or kname in seen_scope_names:
            continue
        pat = f"{lpath}/**"
        target_dir = root / lpath
        if target_dir.is_dir() and any(p.is_file() for p in target_dir.rglob("*")):
            scope_candidates.append({
                "name": kname,
                "paths": [pat]
            })
            seen_scope_names.add(kname)

    facts["scope_candidates"] = scope_candidates

    agent_files = [n for n in ("AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", "README.md", ".cursorrules") if (root / n).exists()]
    skill_dirs = []
    for d in (".agents/skills", ".claude/skills", ".cursor/rules"):
        if (root / d).is_dir():
            skill_dirs.append({"path": d, "entries": sorted(x.name for x in (root / d).iterdir())[:40]})
    facts["agent_files"] = agent_files
    facts["skill_dirs"] = skill_dirs
    facts["has_profile"] = (root / ".agents" / "project-profile.yaml").exists()

    facts["suggested_mode"] = "existing" if (manifests or len(src_files) >= 3) else "new"
    print(json.dumps(facts, indent=2))


if __name__ == "__main__":
    main()
