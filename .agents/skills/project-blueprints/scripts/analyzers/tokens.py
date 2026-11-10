"""Design tokens analyzer: CSS custom properties, themes, fonts, motion."""
import re
from pathlib import Path
from .common import find_files, read_source_file

ROLE_PATTERNS = [
    ("surface", re.compile(r"surface|bg|background", re.IGNORECASE)),
    ("border", re.compile(r"border|stroke|divider", re.IGNORECASE)),
    ("text", re.compile(r"text|fg|foreground|content", re.IGNORECASE)),
    ("action", re.compile(r"primary|secondary|accent|action|btn|button", re.IGNORECASE)),
    ("chart", re.compile(r"chart|data-viz|viz", re.IGNORECASE)),
    ("spacing", re.compile(r"space|spacing|gap|pad|margin", re.IGNORECASE)),
    ("radius", re.compile(r"radius|rounded", re.IGNORECASE)),
    ("motion", re.compile(r"motion|transition|ease|duration|animation", re.IGNORECASE)),
    ("font", re.compile(r"font|family|weight|size|leading", re.IGNORECASE)),
]


def classify_role(token_name: str) -> str:
    """Classify token into a semantic role."""
    for role, pat in ROLE_PATTERNS:
        if pat.search(token_name):
            return role
    return "other"


def detect(root: Path, profile: dict) -> bool:
    """Return True if CSS, theme, or token files exist."""
    files = find_files(root, {".css", ".scss", ".less", ".ts", ".js"}, max_files=10)
    return bool(files)


def extract(root: Path, profile: dict) -> dict:
    """Extract design tokens across CSS custom properties and theme definitions."""
    facts = []
    candidates = []
    sources = set()

    # Store tokens as: {token_name: {"light": val, "dark": val, "role": role, "evidence": ev}}
    tokens_map = {}
    font_tokens = []
    motion_tokens = []

    css_files = find_files(root, {".css", ".scss", ".less"})
    for rel_path in css_files:
        content = read_source_file(root, rel_path)
        if not content:
            continue
        lines = content.split("\n")
        has_tokens = False

        current_scope = "light"  # default
        in_block = False

        for idx, line in enumerate(lines, start=1):
            s_line = line.strip()

            # Scope detection
            if ":root" in s_line or "[data-theme=\"light\"]" in s_line or "[data-theme='light']" in s_line or "html.light" in s_line:
                current_scope = "light"
                in_block = True
            elif ".dark" in s_line or "[data-theme=\"dark\"]" in s_line or "[data-theme='dark']" in s_line or "html.dark" in s_line or "prefers-color-scheme: dark" in s_line:
                current_scope = "dark"
                in_block = True
            elif "@theme" in s_line:
                current_scope = "theme"
                in_block = True
            elif s_line.startswith("}"):
                in_block = False

            # Match CSS custom properties: --name: value;
            var_match = re.search(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;]+);", s_line)
            if var_match:
                has_tokens = True
                name = var_match.group(1)
                val = var_match.group(2).strip()
                role = classify_role(name)

                if role == "font":
                    font_tokens.append({
                        "name": name,
                        "value": val,
                        "evidence": f"{rel_path}:{idx}"
                    })
                elif role == "motion":
                    motion_tokens.append({
                        "name": name,
                        "value": val,
                        "evidence": f"{rel_path}:{idx}"
                    })

                if name not in tokens_map:
                    tokens_map[name] = {
                        "name": name,
                        "role": role,
                        "light": "unknown",
                        "dark": "unknown",
                        "evidence": f"{rel_path}:{idx}"
                    }

                if current_scope in ("light", "theme"):
                    tokens_map[name]["light"] = val
                    if tokens_map[name]["evidence"].endswith(":1") or current_scope == "light":
                        tokens_map[name]["evidence"] = f"{rel_path}:{idx}"
                elif current_scope == "dark":
                    tokens_map[name]["dark"] = val

        if has_tokens:
            sources.add(rel_path)

    # JS/TS motion tokens
    js_files = find_files(root, {".js", ".ts"})
    for rel_path in js_files:
        if "motion" in rel_path.lower() or "transition" in rel_path.lower() or "animation" in rel_path.lower():
            content = read_source_file(root, rel_path)
            lines = content.split("\n")
            for idx, line in enumerate(lines, start=1):
                m_export = re.search(r"export\s+const\s+([A-Za-z0-9_]+)\s*=\s*(\{.*?\}|\[.*?\]|[0-9.]+|['\"][^'\"]+['\"])", line)
                if m_export:
                    var_name = m_export.group(1)
                    val = m_export.group(2)
                    motion_tokens.append({
                        "name": f"JS Motion: {var_name}",
                        "value": val[:60],
                        "evidence": f"{rel_path}:{idx}"
                    })
                    sources.add(rel_path)

    # Compile token facts
    for t in sorted(tokens_map.values(), key=lambda x: (x["role"], x["name"])):
        facts.append({
            "name": f"Token: {t['name']}",
            "evidence": t["evidence"],
            "confidence": "high",
            "role": t["role"],
            "light": t["light"],
            "dark": t["dark"],
            "details": [f"Role: {t['role']}", f"Light: {t['light']}", f"Dark: {t['dark']}"]
        })

    return {
        "facts": facts,
        "token_table": sorted(tokens_map.values(), key=lambda x: (x["role"], x["name"])),
        "font_tokens": sorted(font_tokens, key=lambda x: x["name"]),
        "motion_tokens": sorted(motion_tokens, key=lambda x: x["name"]),
        "candidates": candidates,
        "sources": sorted(sources),
        "unsupported": []
    }


def render(data: dict) -> str:
    """Render extracted tokens to markdown format."""
    lines = ["# Design Tokens Blueprint\n"]
    lines.append("Extracted CSS custom properties, role mappings, and theme palettes.\n")

    lines.append("## Token roles and theme values\n")
    if not data["token_table"]:
        lines.append("- No CSS design tokens detected.\n")
    else:
        lines.append("| Token | Role | Light Value | Dark Value | Evidence |")
        lines.append("|---|---|---|---|---|")
        for t in data["token_table"]:
            lines.append(f"| `{t['name']}` | {t['role']} | `{t['light']}` | `{t['dark']}` | `{t['evidence']}` |")

    if data.get("font_tokens"):
        lines.append("\n## Typography tokens\n")
        for ft in data["font_tokens"]:
            lines.append(f"- `{ft['name']}`: `{ft['value']}` (`{ft['evidence']}`)")

    if data.get("motion_tokens"):
        lines.append("\n## Motion tokens\n")
        for mt in data["motion_tokens"]:
            lines.append(f"- `{mt['name']}`: `{mt['value']}` (`{mt['evidence']}`)")

    return "\n".join(lines).strip() + "\n"
