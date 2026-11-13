#!/usr/bin/env python3
"""Collect README facts for a project and print them as JSON.

Usage: python readme_facts.py [--root DIR]

Reads the Build Forge profile, package.json files, pyproject.toml, the git
remote, the license, screenshots, community files, and the existing README.
Suggests a README style and GitHub topics. Reads no .env file.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

try:
    import yaml
except ImportError:  # the facts still work without the profile
    yaml = None

IGNORE_DIRS = {"node_modules", "dist", "build", ".git", ".next", ".nuxt", "coverage", "venv", ".venv",
               "__pycache__", ".agents", ".claude", ".cursor", ".windsurf", ".gemini", ".vercel", ".netlify"}
UI_FRAMEWORKS = {"react": "React", "vue": "Vue", "svelte": "Svelte", "next": "Next.js", "@angular/core": "Angular",
                 "solid-js": "Solid", "nuxt": "Nuxt", "astro": "Astro", "preact": "Preact"}
BACKEND_JS = {"express": "Express", "@nestjs/core": "NestJS", "hono": "Hono", "fastify": "Fastify", "koa": "Koa"}
BACKEND_PY = {"fastapi": "FastAPI", "flask": "Flask", "django": "Django"}
TOOLING = {"vite": "Vite", "tailwindcss": "Tailwind CSS", "typescript": "TypeScript", "vitest": "Vitest",
           "jest": "Jest", "firebase": "Firebase", "@supabase/supabase-js": "Supabase", "prisma": "Prisma"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
SHOT_WORDS = ("screenshot", "screen", "preview", "demo", "hero", "banner")
COMMUNITY = ["LICENSE", "LICENSE.md", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md", "SUPPORT.md"]
TOPIC_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")


def walk(root: Path, max_depth: int = 4):
    """Yield (path, relative path) for files, skipping dependency, build, and agent folders."""
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        depth = 0 if rel_dir.as_posix() == "." else len(rel_dir.parts)
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS and depth + 1 < max_depth)
        for name in sorted(filenames):
            rel = rel_dir / name if depth else Path(name)
            yield root / rel, rel


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_profile(root: Path) -> dict:
    prof = root / ".agents" / "project-profile.yaml"
    if yaml is None or not prof.is_file():
        return {}
    try:
        return yaml.safe_load(prof.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def git_repo(root: Path) -> str:
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=root, capture_output=True,
                             text=True, check=False).stdout.strip()
    except OSError:
        return ""
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    return m.group(1) if m else ""


def topicize(name: str) -> str:
    t = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return t[:50]


def readme_headings(path: Path) -> list:
    if not path.is_file():
        return []
    heads = []
    in_code = False
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code and re.match(r"^#{1,3} ", line):
            heads.append(line.strip())
    return heads


def collect(root: Path) -> dict:
    prof = load_profile(root)
    project = prof.get("project") or {}
    stack = prof.get("stack") or {}
    commands = {k: v for k, v in (prof.get("commands") or {}).items() if isinstance(v, str) and v.strip()}
    docs = prof.get("docs") or {}

    packages = []
    deps = {}
    scripts = {}
    pkg_root = load_json(root / "package.json")
    for p, rel in walk(root, max_depth=3):
        if p.name == "package.json" and p.is_file():
            data = load_json(p)
            packages.append(rel.as_posix())
            for section in ("dependencies", "devDependencies", "peerDependencies"):
                deps.update(data.get(section) or {})
            prefix = "" if rel.parent.as_posix() == "." else rel.parent.as_posix() + ": "
            for k in (data.get("scripts") or {}):
                scripts[prefix + k] = data["scripts"][k]

    py_text = ""
    for name in ("pyproject.toml", "requirements.txt"):
        for p, rel in walk(root, max_depth=3):
            if p.name == name and p.is_file():
                py_text += p.read_text(encoding="utf-8", errors="ignore").lower() + "\n"

    ui = sorted({label for key, label in UI_FRAMEWORKS.items() if key in deps})
    backend = sorted({label for key, label in BACKEND_JS.items() if key in deps} |
                     {label for key, label in BACKEND_PY.items() if re.search(rf"\b{key}\b", py_text)})
    tools = sorted({label for key, label in TOOLING.items() if key in deps})
    extension = (root / "manifest.json").is_file() and "manifest_version" in (root / "manifest.json").read_text(
        encoding="utf-8", errors="ignore")
    has_bin = bool(pkg_root.get("bin"))
    is_library = bool(pkg_root.get("main") or pkg_root.get("exports")) and not ui
    static_root = (root / "index.html").is_file() and not packages

    if has_bin or is_library:
        style, reason = "technical", "package exposes a CLI or library entry point"
    elif ui or extension:
        style, reason = "showcase", "user facing app (" + ", ".join(ui or ["browser extension"]) + ")"
        if backend:
            reason += " with a backend (" + ", ".join(backend) + "), add an API section"
    elif backend:
        style, reason = "api", "backend service (" + ", ".join(backend) + ") without its own UI"
    elif static_root:
        style, reason = "minimal", "static site with index.html and no package manager"
    else:
        style, reason = "technical", "no UI or backend framework detected"

    shots = []
    for p, rel in walk(root, max_depth=4):
        if p.suffix.lower() in IMAGE_EXT and any(w in p.name.lower() for w in SHOT_WORDS):
            shots.append(rel.as_posix())
    shots = sorted(shots)[:10]

    readme_path = root / (docs.get("readme") or "README.md")
    license_name = pkg_root.get("license", "")
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt"):
        lp = root / name
        if lp.is_file() and not license_name:
            first = lp.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
            license_name = first[0].strip() if first else ""

    meta = {}
    meta_path = root / ".agents" / "repo-meta.yaml"
    if yaml is not None and meta_path.is_file():
        try:
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            meta = {}

    topic_src = ui + backend + tools + [stack.get("language", ""), stack.get("framework", ""),
                                        stack.get("backend", ""), stack.get("database", ""), stack.get("hosting", "")]
    topics = []
    for t in topic_src:
        tt = topicize(str(t or ""))
        if tt and tt != "none" and TOPIC_RE.match(tt) and tt not in topics:
            topics.append(tt)

    env_names = []
    for p, rel in walk(root, max_depth=3):
        if p.name in (".env.example", ".env.sample", ".env.template") and p.is_file():
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
                if m and m.group(1) not in env_names:
                    env_names.append(m.group(1))

    workflows = sorted(p.name for p in (root / ".github" / "workflows").glob("*.y*ml")) if (
        root / ".github" / "workflows").is_dir() else []

    return {
        "name": project.get("name") or pkg_root.get("name") or root.resolve().name,
        "summary": project.get("summary") or pkg_root.get("description") or "",
        "stack": {k: v for k, v in stack.items() if v and v != "none"},
        "detected": {"ui": ui, "backend": backend, "tools": tools, "browser_extension": bool(extension)},
        "commands": commands,
        "scripts": scripts,
        "package_files": packages,
        "env_variable_names": env_names,
        "license": license_name,
        "homepage": meta.get("homepage") or pkg_root.get("homepage") or "",
        "repo": git_repo(root),
        "screenshots": shots,
        "community_files": [n for n in COMMUNITY if (root / n).is_file()],
        "ci_workflows": workflows,
        "blueprints": sorted(p.stem for p in (root / ".agents" / "blueprints").glob("*.md")) if (
            root / ".agents" / "blueprints").is_dir() else [],
        "readme": {"path": readme_path.relative_to(root).as_posix() if readme_path.is_file() else "",
                   "headings": readme_headings(readme_path)},
        "repo_meta": meta,
        "suggested_style": style,
        "style_reason": reason,
        "suggested_topics": topics[:20],
    }


def main():
    ap = argparse.ArgumentParser(description="Collect README facts for a project.")
    ap.add_argument("--root", default=".", help="Project root")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    if not root.is_dir():
        sys.exit(f"ERROR: not a folder: {root}")
    print(json.dumps(collect(root), indent=2))


if __name__ == "__main__":
    main()
