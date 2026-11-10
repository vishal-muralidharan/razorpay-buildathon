"""Config analyzer: environment variable names, scripts, and route definitions."""
import json
import re
from pathlib import Path
from .common import find_files, read_source_file


def detect(root: Path, profile: dict) -> bool:
    """Return True if config, package.json, or source files exist."""
    return (root / "package.json").is_file() or bool(find_files(root, {".ts", ".js", ".json"}, max_files=5))


def extract(root: Path, profile: dict) -> dict:
    """Extract environment variable names, package scripts, and route mappings."""
    facts = []
    candidates = []
    sources = set()

    env_vars = set()
    scripts = []
    routes = []

    # 1. Read .env.example if present (names only, never values)
    env_example = root / ".env.example"
    if env_example.is_file():
        content = read_source_file(root, ".env.example")
        for idx, line in enumerate(content.split("\n"), start=1):
            s_line = line.strip()
            if s_line and not s_line.startswith("#") and "=" in s_line:
                var_name = s_line.split("=")[0].strip()
                if var_name:
                    env_vars.add((var_name, f".env.example:{idx}"))
        sources.add(".env.example")

    # 2. Package scripts
    pkg_file = root / "package.json"
    if pkg_file.is_file():
        try:
            data = json.loads(pkg_file.read_text(encoding="utf-8"))
            pkg_scripts = data.get("scripts", {})
            for sname, scmd in sorted(pkg_scripts.items()):
                scripts.append({
                    "name": sname,
                    "command": scmd,
                    "evidence": "package.json:1"
                })
            sources.add("package.json")
        except Exception:
            pass

    # 3. Code files: scan for process.env.X, import.meta.env.X and routes
    code_files = find_files(root, {".ts", ".tsx", ".js", ".jsx"})
    for rel_path in code_files:
        content = read_source_file(root, rel_path)
        if not content:
            continue
        lines = content.split("\n")
        has_config = False

        for idx, line in enumerate(lines, start=1):
            # process.env.VAR
            matches_proc = re.findall(r"\bprocess\.env\.([A-Za-z0-9_]+)\b", line)
            for m in matches_proc:
                env_vars.add((m, f"{rel_path}:{idx}"))
                has_config = True

            # import.meta.env.VAR
            matches_meta = re.findall(r"\bimport\.meta\.env\.([A-Za-z0-9_]+)\b", line)
            for m in matches_meta:
                env_vars.add((m, f"{rel_path}:{idx}"))
                has_config = True

            # Express / framework routes: app.get('/path', ...), router.post('/path', ...)
            route_match = re.search(r"\b(?:app|router)\.(get|post|put|delete|patch)\(\s*['\"]([^'\"]+)['\"]", line)
            if route_match:
                routes.append({
                    "method": route_match.group(1).upper(),
                    "path": route_match.group(2),
                    "evidence": f"{rel_path}:{idx}"
                })
                has_config = True

        if has_config:
            sources.add(rel_path)

    # Compile facts
    for ev_name, ev_loc in sorted(env_vars, key=lambda x: x[0]):
        facts.append({
            "name": f"Env Var: {ev_name}",
            "evidence": ev_loc,
            "confidence": "high",
            "details": ["Referenced in application code or .env.example"]
        })

    for s in sorted(scripts, key=lambda x: x["name"]):
        facts.append({
            "name": f"Script: {s['name']}",
            "evidence": s["evidence"],
            "confidence": "high",
            "details": [f"Command: {s['command']}"]
        })

    for r in sorted(routes, key=lambda x: (x["path"], x["method"])):
        facts.append({
            "name": f"Route: {r['method']} {r['path']}",
            "evidence": r["evidence"],
            "confidence": "high",
            "details": [f"Handler defined in {r['evidence']}"]
        })

    return {
        "facts": sorted(facts, key=lambda x: (x["name"], x["evidence"])),
        "env_vars": sorted(list(env_vars), key=lambda x: x[0]),
        "scripts": sorted(scripts, key=lambda x: x["name"]),
        "routes": sorted(routes, key=lambda x: (x["path"], x["method"])),
        "candidates": candidates,
        "sources": sorted(sources),
        "unsupported": []
    }


def render(data: dict) -> str:
    """Render config facts to markdown format."""
    lines = ["# Config Blueprint\n"]
    lines.append("Extracted environment variables, project scripts, and route mappings.\n")

    lines.append("## Environment variables\n")
    if not data["env_vars"]:
        lines.append("- No environment variable references detected.\n")
    else:
        for ev_name, ev_loc in data["env_vars"]:
            lines.append(f"- `{ev_name}` (referenced: `{ev_loc}`)")

    lines.append("\n## Package scripts\n")
    if not data["scripts"]:
        lines.append("- No package scripts found.\n")
    else:
        for s in data["scripts"]:
            lines.append(f"- `{s['name']}`: `{s['command']}` (`{s['evidence']}`)")

    lines.append("\n## Routes\n")
    if not data["routes"]:
        lines.append("- No explicit server routes detected.\n")
    else:
        for r in data["routes"]:
            lines.append(f"- `{r['method']} {r['path']}` (`{r['evidence']}`)")

    return "\n".join(lines).strip() + "\n"
