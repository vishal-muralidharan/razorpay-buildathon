#!/usr/bin/env python3
"""Check a project README and its GitHub repo meta.

Usage:
  python check_readme.py [--root DIR] [--readme PATH] [--style STYLE] [--strict]
  python check_readme.py [--root DIR] --print-gh

Checks the sections required by the style, that every npm, pnpm, yarn, and bun
script in the README exists, that relative links and images resolve, that no
secret-like value is present, and the GitHub description, homepage, and topic
limits in .agents/repo-meta.yaml. --print-gh prints the gh repo edit commands
for the user to run. Exit 1 when an error is found.
"""
import argparse
import json
import os
import re
import shlex
import sys
from pathlib import Path

sys.dont_write_bytecode = True

try:
    import yaml
except ImportError:
    yaml = None

DESCRIPTION_MAX = 350
TOPICS_MAX = 20
TOPIC_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")
STYLES = ("technical", "showcase", "minimal", "api")
REQUIRED = {
    "technical": [("install", "installation", "getting started"), ("usage", "quick start", "quickstart"),
                  ("requirements", "compatibility", "prerequisites"), ("license",)],
    "showcase": [("features", "what it does", "highlights"),
                 ("getting started", "run locally", "quick start", "setup", "installation"),
                 ("tech stack", "built with", "stack")],
    "minimal": [],
    "api": [("endpoints", "api", "routes"), ("setup", "getting started", "run locally", "installation"),
            ("environment", "configuration", "config")],
}
IGNORE_DIRS = {"node_modules", "dist", "build", ".git", ".next", "coverage", "venv", ".venv", "__pycache__"}
SECRET_PATTERNS = [
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("Razorpay live key", re.compile(r"rzp_live_[A-Za-z0-9]{10,}")),
    ("Stripe secret key", re.compile(r"sk_live_[A-Za-z0-9]{10,}")),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("npm token", re.compile(r"npm_[A-Za-z0-9]{30,}")),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]
PLACEHOLDER_RE = re.compile(r"\bTODO\b|\{\{|lorem ipsum|\[CONFIRM", re.IGNORECASE)
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\U0001F000-\U0001F2FF]")
SCRIPT_RE = re.compile(r"\b(npm run|pnpm run|pnpm|yarn run|yarn|bun run)\s+([A-Za-z0-9:_\-]+)")
PM_BUILTINS = {"install", "add", "remove", "dlx", "exec", "create", "init", "ci", "i", "x", "test", "start",
               "global", "link", "publish", "outdated", "update", "upgrade", "why", "audit", "list", "run"}
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
IMG_ALT_EMPTY_RE = re.compile(r"!\[\s*\]\(")
HTML_SRC_RE = re.compile(r"""<(?:img|source)\b[^>]*\b(?:src|srcset)=["']([^"']+)["']""", re.IGNORECASE)


def load_yaml(path: Path) -> dict:
    if yaml is None or not path.is_file():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return {"_error": str(exc)}


def package_scripts(root: Path) -> set:
    names = set()
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".") and len(rel.parts) < 3]
        if "package.json" in filenames:
            try:
                data = json.loads((Path(dirpath) / "package.json").read_text(encoding="utf-8"))
                names.update((data.get("scripts") or {}).keys())
            except Exception:
                pass
    return names


def split_code(text: str):
    """Return (prose lines with line numbers, code lines with line numbers)."""
    prose, code = [], []
    in_code = False
    for n, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        (code if in_code else prose).append((n, line))
    return prose, code


def norm_heading(line: str) -> str:
    h = re.sub(r"^#+\s*", "", line)
    h = EMOJI_RE.sub("", h)
    h = re.sub(r"[*_`:]", "", h)
    return re.sub(r"\s+", " ", h).strip().lower()


def check(root: Path, readme: Path, style: str, meta: dict, strict: bool):
    errors, warnings = [], []
    if not readme.is_file():
        return [f"README not found at {readme}"], []
    text = readme.read_text(encoding="utf-8", errors="ignore")
    if not text.strip():
        return ["README is empty"], []
    prose, code = split_code(text)

    h1 = [n for n, line in prose if re.match(r"^# \S", line)]
    if not h1:
        errors.append("no title: add 1 level-1 heading (# Name)")
    elif len(h1) > 1:
        warnings.append(f"{len(h1)} level-1 headings, expected 1 (lines {', '.join(map(str, h1))})")

    headings = [norm_heading(line) for _, line in prose if re.match(r"^#{2,3} ", line)]
    for options in REQUIRED.get(style, []):
        if not any(any(re.search(r"\b" + re.escape(o) + r"\b", h) for o in options) for h in headings):
            errors.append(f"missing section for style '{style}': {' or '.join(options)}")

    if h1:
        after = [line for n, line in prose if n > h1[0]]
        para = ""
        for line in after:
            s = line.strip()
            if not s:
                if para:
                    break
                continue
            if s.startswith(("#", "!", "<", "[!", "|", ">")) or re.match(r"^\[!\[", s):
                if para:
                    break
                continue
            para += " " + s
        if not para.strip():
            errors.append("no pitch: add 1 or 2 sentences right after the title")
        elif len(para.strip()) > 400:
            warnings.append(f"pitch is {len(para.strip())} characters, keep it under 400")

    known = package_scripts(root)
    command_lines = list(code) + [(n, seg) for n, line in prose for seg in re.findall(r"`([^`]+)`", line)]
    for n, line in command_lines:
        for m in SCRIPT_RE.finditer(line):
            name = m.group(2)
            if m.group(1) in ("pnpm", "yarn") and name in PM_BUILTINS:
                continue
            if m.group(1) in ("npm run", "pnpm run", "yarn run", "bun run") or name not in PM_BUILTINS:
                if known and name not in known:
                    errors.append(f"line {n}: script '{name}' is not in any package.json")

    base = readme.parent
    for n, line in prose:
        targets = [m.group(1) for m in LINK_RE.finditer(line)] + [m.group(1) for m in HTML_SRC_RE.finditer(line)]
        for target in targets:
            t = target.strip().split(" ")[0]
            if re.match(r"^(https?:|mailto:|#|data:|//)", t):
                continue
            path = t.split("#")[0].split("?")[0]
            if path and not (base / path).exists():
                errors.append(f"line {n}: broken relative link or image: {path}")
        if IMG_ALT_EMPTY_RE.search(line):
            warnings.append(f"line {n}: image without alt text")

    for label, pat in SECRET_PATTERNS:
        for n, line in enumerate(text.splitlines(), 1):
            if pat.search(line):
                errors.append(f"line {n}: looks like a {label}. Remove it and rotate it if it was real")

    for n, line in prose:
        if PLACEHOLDER_RE.search(line):
            (errors if strict else warnings).append(f"line {n}: placeholder left: {line.strip()[:80]}")

    if style in ("technical", "api"):
        emoji_heads = [n for n, line in prose if line.startswith("#") and EMOJI_RE.search(line)]
        if emoji_heads:
            warnings.append(f"style '{style}' uses no emojis in headings (lines {', '.join(map(str, emoji_heads))})")

    errors_meta, warnings_meta = check_meta(meta)
    return errors + errors_meta, warnings + warnings_meta


def check_meta(meta: dict):
    errors, warnings = [], []
    if not meta:
        warnings.append("no .agents/repo-meta.yaml: add description, homepage, and topics")
        return errors, warnings
    if "_error" in meta:
        return [f".agents/repo-meta.yaml does not parse: {meta['_error']}"], []
    desc = str(meta.get("description") or "")
    if not desc.strip():
        errors.append("repo-meta: description is empty")
    elif len(desc) > DESCRIPTION_MAX:
        errors.append(f"repo-meta: description is {len(desc)} characters, the limit is {DESCRIPTION_MAX}")
    if "\n" in desc:
        errors.append("repo-meta: description must be 1 line")
    home = str(meta.get("homepage") or "")
    if home and not home.startswith("https://"):
        errors.append(f"repo-meta: homepage must start with https:// ({home})")
    topics = meta.get("topics") or []
    if not isinstance(topics, list):
        errors.append("repo-meta: topics must be a list")
        topics = []
    if len(topics) > TOPICS_MAX:
        errors.append(f"repo-meta: {len(topics)} topics, the limit is {TOPICS_MAX}")
    for t in topics:
        if not TOPIC_RE.match(str(t)):
            errors.append(f"repo-meta: topic '{t}' must be lowercase letters, digits, and hyphens, 50 characters at most")
    if len(set(map(str, topics))) != len(topics):
        warnings.append("repo-meta: duplicate topics")
    if meta.get("style") and meta.get("style") not in STYLES:
        errors.append(f"repo-meta: style must be one of {', '.join(STYLES)}")
    return errors, warnings


def suggested_style(root: Path) -> str:
    """Style suggested by readme_facts.py, used when neither --style nor repo-meta sets one."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import readme_facts
        return readme_facts.collect(root).get("suggested_style") or "technical"
    except Exception:
        return "technical"


def print_gh(meta: dict) -> int:
    errors, _ = check_meta(meta)
    if errors:
        for e in errors:
            print(f"ERROR {e}")
        return 1
    parts = ["gh repo edit", "--description " + shlex.quote(str(meta.get("description", "")))]
    if meta.get("homepage"):
        parts.append("--homepage " + shlex.quote(str(meta["homepage"])))
    topics = [str(t) for t in (meta.get("topics") or [])]
    if topics:
        parts.append("--add-topic " + shlex.quote(",".join(topics)))
    print("Run these yourself from the project folder:")
    print(" ".join(parts))
    print("gh repo view --json description,homepageUrl,repositoryTopics")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Check a project README and its GitHub repo meta.")
    ap.add_argument("--root", default=".", help="Project root")
    ap.add_argument("--readme", default=None, help="README path. Defaults to docs.readme in the profile, then README.md")
    ap.add_argument("--style", default=None, help="Overrides style in .agents/repo-meta.yaml: technical, showcase, minimal, or api")
    ap.add_argument("--strict", action="store_true", help="Treat placeholders and TODOs as errors")
    ap.add_argument("--print-gh", action="store_true", help="Print the gh repo edit commands and exit")
    a = ap.parse_args()

    root = Path(a.root).resolve()
    meta = load_yaml(root / ".agents" / "repo-meta.yaml")
    if a.print_gh:
        sys.exit(print_gh(meta))

    profile = load_yaml(root / ".agents" / "project-profile.yaml")
    readme_rel = a.readme or ((profile.get("docs") or {}).get("readme") if isinstance(profile, dict) else None) or "README.md"
    if a.style and a.style not in STYLES:
        sys.exit(f"ERROR: --style must be one of {', '.join(STYLES)}")
    style = a.style or meta.get("style") or suggested_style(root)
    if style not in STYLES:
        style = "technical"
    errors, warnings = check(root, root / readme_rel, style, meta, a.strict)
    for e in errors:
        print(f"ERROR {e}")
    for w in warnings:
        print(f"WARN  {w}")
    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s). Style: {style}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
