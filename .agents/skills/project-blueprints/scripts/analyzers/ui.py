"""UI component analyzer: components, props, variants, state primitives, and form controls."""
import re
from pathlib import Path
from .common import find_files, read_source_file

STATE_PRIMITIVES = {
    "Skeleton", "Spinner", "Loading", "Empty", "Error",
    "Toast", "Alert", "Modal", "Sheet"
}

LOW_LEVEL_WIDGETS = [
    "Calendar", "Popover", "Listbox", "Menu", "Dropdown",
    "Sheet", "Dialog", "Modal", "Tabs", "Combobox"
]

FAMILY_LOW_LEVEL_WIDGETS = {
    "date": ["Calendar", "Popover"],
    "time": ["Popover", "Listbox", "Dropdown"],
    "color": ["Popover"],
    "select": ["Listbox", "Dropdown", "Menu", "Popover", "Combobox"],
    "dialog": ["Dialog", "Modal", "Sheet", "Alert"],
    "textarea": [],
    "range": [],
    "file": [],
    "checkbox": [],
    "radio": [],
}

THEMED_PRIMITIVE_NAMES = {
    "date": ["DatePicker", "DateInput", "DateField"],
    "time": ["TimePicker", "TimeInput"],
    "color": ["ColorPicker", "ColorInput"],
    "select": ["Select", "ComboboxSelect"],
    "dialog": ["ConfirmDialog", "AlertDialog", "Toast"],
    "textarea": ["Textarea"],
    "range": ["Slider", "RangeSlider"],
    "file": ["FileInput", "FileUploader", "UploadDropzone"],
    "checkbox": ["Checkbox"],
    "radio": ["RadioGroup", "Radio"],
}

NATIVE_CONTROL_PATTERNS = {
    "date": re.compile(r'(?<![\w-])type\s*=\s*(?:\{\s*)?["\'`](?:date|month|week|datetime-local)["\'`]'),
    "time": re.compile(r'(?<![\w-])type\s*=\s*(?:\{\s*)?["\'`]time["\'`]'),
    "color": re.compile(r'(?<![\w-])type\s*=\s*(?:\{\s*)?["\'`]color["\'`]'),
    "select": re.compile(r'<select\b'),
    "textarea": re.compile(r'<textarea\b'),
    "range": re.compile(r'(?<![\w-])type\s*=\s*(?:\{\s*)?["\'`]range["\'`]'),
    "file": re.compile(r'(?<![\w-])type\s*=\s*(?:\{\s*)?["\'`]file["\'`]'),
    "checkbox": re.compile(r'(?<![\w-])type\s*=\s*(?:\{\s*)?["\'`]checkbox["\'`]'),
    "radio": re.compile(r'(?<![\w-])type\s*=\s*(?:\{\s*)?["\'`]radio["\'`]'),
    "dialog": re.compile(r'(?<![\w.$])(?:window\.)?(?:alert|confirm|prompt)\s*\('),
}

DYNAMIC_INPUT_PATTERN = re.compile(r'<[iI]nput[^>]*type\s*=\s*\{\s*([A-Za-z0-9_$.]+)\s*\}')


def detect(root: Path, profile: dict) -> bool:
    """Return True if UI components exist in project."""
    files = find_files(root, {".tsx", ".jsx", ".vue", ".svelte", ".html", ".js", ".ts"}, max_files=5)
    return bool(files)


def extract(root: Path, profile: dict) -> dict:
    """Extract component catalog, state primitives, low-level widgets, and form controls."""
    facts = []
    candidates = []
    sources = set()

    state_primitives_found = []
    components = []

    comp_dirs = profile.get("design", {}).get("component_dirs", ["src/components/ui", "src/components", "components", "src/ui", "ui"])
    if isinstance(comp_dirs, str):
        comp_dirs = [comp_dirs]

    comp_dir_prefixes = []
    for d in comp_dirs:
        cleaned = d.replace("\\", "/")
        if cleaned.endswith("/*"):
            cleaned = cleaned[:-2]
        elif cleaned.endswith("/") or cleaned.endswith("*"):
            cleaned = cleaned[:-1]
        if cleaned:
            comp_dir_prefixes.append(cleaned)

    ui_files = find_files(root, {".tsx", ".jsx", ".vue", ".svelte", ".html", ".js", ".ts"})

    # 1. Discover low-level widgets in component folders
    low_level_found = {}
    for rel_path in ui_files:
        is_comp = any(rel_path.startswith(pfx) for pfx in comp_dir_prefixes) or len(comp_dir_prefixes) == 0
        if not is_comp:
            continue
        stem = Path(rel_path).stem
        for widget in LOW_LEVEL_WIDGETS:
            if widget.lower() == stem.lower() or widget in stem:
                if widget not in low_level_found:
                    low_level_found[widget] = f"{rel_path}:1"

    # 2. Discover themed primitives in component folders
    themed_primitives_found = {}
    for family, pnames in THEMED_PRIMITIVE_NAMES.items():
        for rel_path in ui_files:
            is_comp = any(rel_path.startswith(pfx) for pfx in comp_dir_prefixes) or len(comp_dir_prefixes) == 0
            if not is_comp:
                continue
            stem = Path(rel_path).stem
            for pn in pnames:
                if pn.lower() == stem.lower() or stem.endswith(pn):
                    if family not in themed_primitives_found:
                        themed_primitives_found[family] = rel_path
                    break

    # 3. Detect native control usages outside primitive folders
    native_uses_by_family = {fam: [] for fam in NATIVE_CONTROL_PATTERNS}
    dynamic_uses = []

    for rel_path in ui_files:
        content = read_source_file(root, rel_path)
        if not content:
            continue
        lines = content.split("\n")
        has_ui = False

        is_primitive_folder = any(rel_path.startswith(pfx) for pfx in comp_dir_prefixes)

        # Scan for component catalog inside component folders
        if is_primitive_folder:
            for idx, line in enumerate(lines, start=1):
                comp_match = re.search(r"export\s+(?:default\s+)?(?:function|const)\s+([A-Z][A-Za-z0-9]+)", line)
                if comp_match:
                    cname = comp_match.group(1)
                    props_type = "unknown"
                    prop_match = re.search(rf"(?:interface|type)\s+({cname}Props|Props)\b", content)
                    if prop_match:
                        props_type = prop_match.group(1)

                    variants = []
                    v_matches = re.findall(r"(?:variant|size|intent)\s*[:=]\s*['\"]([A-Za-z0-9_-]+)['\"]", content)
                    for vm in set(v_matches):
                        variants.append(vm)

                    comp_fact = {
                        "name": f"Component: {cname}",
                        "evidence": f"{rel_path}:{idx}",
                        "confidence": "high",
                        "props": props_type,
                        "variants": sorted(variants)[:6],
                        "details": [
                            f"File: {rel_path}",
                            f"Props Type: {props_type}",
                            f"Variants: {', '.join(sorted(variants)[:6]) or 'none'}"
                        ]
                    }
                    components.append(comp_fact)
                    facts.append(comp_fact)
                    has_ui = True

        # Scan for state primitives
        for idx, line in enumerate(lines, start=1):
            if 'role="alert"' in line or "role='alert'" in line:
                state_primitives_found.append({
                    "name": "role='alert'",
                    "evidence": f"{rel_path}:{idx}"
                })
                has_ui = True

        base_name = Path(rel_path).stem
        for prim in STATE_PRIMITIVES:
            if prim.lower() in base_name.lower():
                state_primitives_found.append({
                    "name": prim,
                    "evidence": f"{rel_path}:1"
                })
                has_ui = True

        # Scan for native controls outside primitive folders
        if not is_primitive_folder:
            for idx, line in enumerate(lines, start=1):
                # Dynamic input type check: type={kind}
                dyn_match = DYNAMIC_INPUT_PATTERN.search(line)
                if dyn_match:
                    val = dyn_match.group(1)
                    if not (val.startswith(('"', "'", "`"))):
                        dynamic_uses.append(f"{rel_path}:{idx}")
                        has_ui = True

                for fam, rx in NATIVE_CONTROL_PATTERNS.items():
                    if rx.search(line):
                        native_uses_by_family[fam].append(f"{rel_path}:{idx}")
                        has_ui = True

        if has_ui:
            sources.add(rel_path)

    components.sort(key=lambda x: (x["name"], x["evidence"]))
    state_primitives_found.sort(key=lambda x: (x["name"], x["evidence"]))

    # 4. Build Form controls table
    form_controls_table = []
    families_to_report = ["date", "time", "color", "select", "dialog", "textarea", "range", "file", "checkbox", "radio"]

    for fam in families_to_report:
        themed_path = themed_primitives_found.get(fam, "none")
        native_list = native_uses_by_family.get(fam, [])
        low_level_candidates = FAMILY_LOW_LEVEL_WIDGETS.get(fam, [])
        matching_widgets = [w for w in low_level_candidates if w in low_level_found]

        has_primitive = (themed_path != "none")
        has_native_uses = len(native_list) > 0
        has_low_level = len(matching_widgets) > 0

        # Calculate status
        if has_native_uses and not has_primitive and has_low_level:
            status = "gap, violation"
        elif has_native_uses and has_primitive:
            status = "violation"
        elif has_native_uses and not has_primitive:
            status = "violation"
        elif not has_native_uses and not has_primitive and has_low_level:
            status = "gap"
        else:
            status = "ok"

        # Special case: dynamic input in date/text
        if fam == "date" and not has_native_uses and len(dynamic_uses) > 0:
            status = "review"

        first_3_evidence = ", ".join(native_list[:3]) if native_list else "none"
        form_controls_table.append({
            "family": fam,
            "themed_primitive": themed_path,
            "native_uses_count": len(native_list),
            "native_uses_evidence": native_list[:3],
            "low_level_widgets": matching_widgets,
            "status": status
        })

    # Add dynamic type entry if dynamic uses exist
    if dynamic_uses:
        form_controls_table.append({
            "family": "dynamic-type",
            "themed_primitive": "none",
            "native_uses_count": len(dynamic_uses),
            "native_uses_evidence": dynamic_uses[:3],
            "low_level_widgets": [],
            "status": "review"
        })

    # 5. Build Candidates: violations -> rule candidates; gaps -> process candidates
    for row in form_controls_table:
        fam = row["family"]
        st = row["status"]
        if "violation" in st:
            if fam in ("date", "time", "color"):
                candidates.append({
                    "id": "ui-no-native-pickers",
                    "area": "design",
                    "rule": "Never use native browser date, time, month, week, datetime-local or color inputs. Use the project's themed picker primitives.",
                    "evidence": f"Found {row['native_uses_count']} native picker uses outside primitives: {', '.join(row['native_uses_evidence'])}"
                })
            elif fam == "select":
                candidates.append({
                    "id": "ui-no-native-selects",
                    "area": "design",
                    "rule": "Avoid raw HTML <select>; use the design system Select primitive.",
                    "evidence": f"Found {row['native_uses_count']} native select uses outside primitives: {', '.join(row['native_uses_evidence'])}"
                })
            elif fam == "dialog":
                candidates.append({
                    "id": "ui-no-browser-dialogs",
                    "area": "design",
                    "rule": "Never use alert, confirm or prompt. Use the project's dialog and toast primitives.",
                    "evidence": f"Found {row['native_uses_count']} native dialog uses: {', '.join(row['native_uses_evidence'])}"
                })
            else:
                candidates.append({
                    "id": f"ui-no-native-{fam}",
                    "area": "design",
                    "rule": f"Avoid raw HTML native {fam} control; use the themed primitive.",
                    "evidence": f"Found {row['native_uses_count']} native {fam} uses outside primitives."
                })

        if "gap" in st:
            widget_str = ", ".join(row["low_level_widgets"]) if row["low_level_widgets"] else "low level widget"
            candidates.append({
                "id": f"process-primitive-gap-{fam}",
                "area": "process",
                "rule": "Create the primitive first, in its own commit, before using the control.",
                "evidence": f"Low-level widget ({widget_str}) exists without a themed {fam} primitive."
            })

    # Sort candidates deterministically
    candidates.sort(key=lambda x: (x["area"], x["id"]))

    return {
        "facts": sorted(facts, key=lambda x: (x["name"], x["evidence"])),
        "components": components,
        "state_primitives": state_primitives_found,
        "low_level_widgets": low_level_found,
        "form_controls_table": form_controls_table,
        "candidates": candidates,
        "sources": sorted(sources),
        "unsupported": []
    }


def render(data: dict) -> str:
    """Render extracted UI components, form controls, and state primitives to markdown format."""
    lines = ["# UI Component Blueprint\n"]
    lines.append("Extracted UI components, props contracts, variants, and state primitives.\n")

    lines.append("## Component catalog\n")
    if not data["components"]:
        lines.append("- No exported UI components detected in component directories.\n")
    else:
        for c in data["components"]:
            lines.append(f"- **{c['name']}**")
            lines.append(f"  - Evidence: `{c['evidence']}` (confidence: {c['confidence']})")
            lines.append(f"  - Props: `{c['props']}`")
            lines.append(f"  - Variants: {', '.join(f'`{v}`' for v in c['variants']) or 'none'}")

    lines.append("\n## Form controls\n")
    fc_table = data.get("form_controls_table", [])
    if fc_table:
        lines.append("| Control family | Themed primitive | Native uses | Status |")
        lines.append("|---|---|---|---|")
        for row in fc_table:
            ev_str = f"{row['native_uses_count']}"
            if row["native_uses_evidence"]:
                ev_str += f" ({', '.join(row['native_uses_evidence'])})"
            lines.append(f"| {row['family']} | {row['themed_primitive']} | {ev_str} | {row['status']} |")

    lines.append("\n## State primitives and alerts\n")
    if not data["state_primitives"]:
        lines.append("- No specialized state primitives detected.\n")
    else:
        for sp in data["state_primitives"]:
            lines.append(f"- Primitive: `{sp['name']}` (`{sp['evidence']}`)")

    low_level = data.get("low_level_widgets", {})
    if low_level:
        lines.append("\n## Low level widgets\n")
        for wname, wev in sorted(low_level.items()):
            lines.append(f"- `{wname}`: `{wev}`")

    return "\n".join(lines).strip() + "\n"
