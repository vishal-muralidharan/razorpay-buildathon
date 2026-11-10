"""Layout and responsive design analyzer: breakpoints, shells, and mobile constraints."""
import re
from pathlib import Path
from .common import find_files, read_source_file

NAV_PATTERNS = ["bottom", "sidebar", "rail", "header", "topbar", "navbar", "navigation"]


def detect(root: Path, profile: dict) -> bool:
    """Return True if layout, CSS, or navigation files exist."""
    files = find_files(root, {".css", ".scss", ".tsx", ".jsx", ".html"}, max_files=10)
    return bool(files)


def extract(root: Path, profile: dict) -> dict:
    """Extract layout breakpoints, shells, and mobile constraints."""
    facts = []
    candidates = []
    sources = set()

    breakpoints = []
    nav_components = []
    mobile_constraints = []

    css_html_files = find_files(root, {".css", ".scss", ".html", ".tsx", ".jsx", ".ts", ".js"})
    for rel_path in css_html_files:
        content = read_source_file(root, rel_path)
        if not content:
            continue
        lines = content.split("\n")
        has_layout = False

        # Navigation component detection
        base_name = Path(rel_path).stem
        for pat in NAV_PATTERNS:
            if pat in base_name.lower():
                nav_components.append({
                    "name": f"Navigation Shell: {base_name}",
                    "evidence": f"{rel_path}:1"
                })
                has_layout = True
                break

        for idx, line in enumerate(lines, start=1):
            s_line = line.strip()

            # 1. Media queries (min/max width)
            media_match = re.search(r"@media[^{]*\((?:min-width|max-width)\s*:\s*([^)]+)\)", s_line)
            if media_match:
                bp_val = media_match.group(1).strip()
                breakpoints.append({
                    "name": f"Breakpoint: {bp_val}",
                    "evidence": f"{rel_path}:{idx}",
                    "value": bp_val
                })
                has_layout = True

            # 2. Viewport meta
            if "<meta" in s_line and "viewport" in s_line:
                mobile_constraints.append({
                    "name": "Viewport meta tag",
                    "evidence": f"{rel_path}:{idx}",
                    "detail": s_line[:80]
                })
                has_layout = True

            # 3. safe-area-inset
            if "safe-area-inset" in s_line:
                mobile_constraints.append({
                    "name": "Safe area insets constraint",
                    "evidence": f"{rel_path}:{idx}",
                    "detail": s_line[:80]
                })
                has_layout = True

            # 4. dvh / dynamic viewport units
            if re.search(r"\b\d+dvh\b", s_line):
                mobile_constraints.append({
                    "name": "Dynamic viewport unit (dvh)",
                    "evidence": f"{rel_path}:{idx}",
                    "detail": s_line[:80]
                })
                has_layout = True

            # 5. Input font-size iOS zoom rules
            if ("input" in s_line.lower() or "textarea" in s_line.lower()) and "font-size" in s_line and "16px" in s_line:
                mobile_constraints.append({
                    "name": "Mobile input font-size constraint (>=16px)",
                    "evidence": f"{rel_path}:{idx}",
                    "detail": s_line[:80]
                })
                has_layout = True

            # 6. Touch target utilities
            if "min-h-[44px]" in s_line or "min-w-[44px]" in s_line or "min-h-11" in s_line or "touch-target" in s_line:
                mobile_constraints.append({
                    "name": "Touch target constraint (44px)",
                    "evidence": f"{rel_path}:{idx}",
                    "detail": s_line[:80]
                })
                has_layout = True

        if has_layout:
            sources.add(rel_path)

    # Compile facts
    # Unique breakpoints
    seen_bp = set()
    for bp in sorted(breakpoints, key=lambda x: (x["value"], x["evidence"])):
        if bp["value"] not in seen_bp:
            seen_bp.add(bp["value"])
            facts.append({
                "name": bp["name"],
                "evidence": bp["evidence"],
                "confidence": "high",
                "details": [f"Value: {bp['value']}"]
            })

    for nc in sorted(nav_components, key=lambda x: (x["name"], x["evidence"])):
        facts.append({
            "name": nc["name"],
            "evidence": nc["evidence"],
            "confidence": "high",
            "details": ["Navigation shell element"]
        })

    for mc in sorted(mobile_constraints, key=lambda x: (x["name"], x["evidence"])):
        facts.append({
            "name": mc["name"],
            "evidence": mc["evidence"],
            "confidence": "high",
            "details": [mc["detail"]]
        })

    return {
        "facts": sorted(facts, key=lambda x: (x["name"], x["evidence"])),
        "breakpoints": sorted(breakpoints, key=lambda x: x["evidence"]),
        "nav_components": sorted(nav_components, key=lambda x: x["evidence"]),
        "mobile_constraints": sorted(mobile_constraints, key=lambda x: x["evidence"]),
        "candidates": candidates,
        "sources": sorted(sources),
        "unsupported": []
    }


def render(data: dict) -> str:
    """Render layout facts to markdown format."""
    lines = ["# Layout Blueprint\n"]
    lines.append("Extracted responsive breakpoints, navigation shells, and mobile viewport constraints.\n")

    lines.append("## Breakpoints\n")
    if not data["breakpoints"]:
        lines.append("- No explicit CSS media query breakpoints detected.\n")
    else:
        for bp in data["breakpoints"]:
            lines.append(f"- `{bp['name']}`: evidence `{bp['evidence']}`")

    lines.append("\n## Navigation shells\n")
    if not data["nav_components"]:
        lines.append("- No dedicated navigation shells detected.\n")
    else:
        for nc in data["nav_components"]:
            lines.append(f"- `{nc['name']}` (`{nc['evidence']}`)")

    lines.append("\n## Mobile and viewport constraints\n")
    if not data["mobile_constraints"]:
        lines.append("- No mobile viewport constraints detected.\n")
    else:
        for mc in data["mobile_constraints"]:
            lines.append(f"- {mc['name']}: `{mc['evidence']}` (`{mc['detail']}`)")

    return "\n".join(lines).strip() + "\n"
