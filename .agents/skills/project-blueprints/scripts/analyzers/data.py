"""Data area analyzer: tables, models, types, schemas, and storage keys."""
import re
from pathlib import Path
from .common import find_files, read_source_file


def detect(root: Path, profile: dict) -> bool:
    """Return True if project has data or schema files."""
    sql_files = find_files(root, {".sql"}, max_files=5)
    ts_files = find_files(root, {".ts", ".tsx", ".js", ".jsx"}, max_files=10)
    prisma_files = find_files(root, {".prisma"}, max_files=5)
    return bool(sql_files or prisma_files or ts_files)


def extract(root: Path, profile: dict) -> dict:
    """Extract data facts from project source files."""
    facts = []
    signals = []
    candidates = []
    sources = set()

    # 1. SQL Tables & Policies
    sql_files = find_files(root, {".sql"})
    for rel_path in sql_files:
        sources.add(rel_path)
        content = read_source_file(root, rel_path)
        lines = content.split("\n")
        in_table = None
        table_cols = []
        table_start_line = 0

        for idx, line in enumerate(lines, start=1):
            table_match = re.search(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_.\"']+)\s*\(", line, re.IGNORECASE)
            if table_match:
                in_table = table_match.group(1).strip("\"'`")  # strip-chars-ok: trim quote and backtick delimiters
                table_cols = []
                table_start_line = idx
                continue

            if in_table:
                if line.strip().startswith(");") or (line.strip() == ")" and idx < len(lines)):
                    facts.append({
                        "name": f"SQL Table: {in_table}",
                        "evidence": f"{rel_path}:{table_start_line}",
                        "confidence": "high",
                        "details": table_cols[:12]
                    })
                    in_table = None
                else:
                    col_line = line.strip().rstrip(",")
                    if col_line and not col_line.startswith("--"):
                        table_cols.append(col_line)

            # RLS checks
            rls_match = re.search(r"ALTER\s+TABLE\s+([A-Za-z0-9_.\"']+)\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY", line, re.IGNORECASE)
            if rls_match:
                t_name = rls_match.group(1).strip("\"'`")  # strip-chars-ok: trim quote and backtick delimiters
                facts.append({
                    "name": f"RLS Enabled: {t_name}",
                    "evidence": f"{rel_path}:{idx}",
                    "confidence": "high",
                    "details": ["Row level security is enabled"]
                })

            policy_match = re.search(r"CREATE\s+POLICY\s+([\"'][^\"']+[\"']|[A-Za-z0-9_]+)\s+ON\s+([A-Za-z0-9_.\"']+)", line, re.IGNORECASE)
            if policy_match:
                p_name = policy_match.group(1).strip("\"'")  # strip-chars-ok: trim quotes
                t_name = policy_match.group(2).strip("\"'`")  # strip-chars-ok: trim quote and backtick delimiters
                facts.append({
                    "name": f"Policy: {p_name} on {t_name}",
                    "evidence": f"{rel_path}:{idx}",
                    "confidence": "high",
                    "details": [line.strip()]
                })

    # 2. Prisma Models
    prisma_files = find_files(root, {".prisma"})
    for rel_path in prisma_files:
        sources.add(rel_path)
        content = read_source_file(root, rel_path)
        lines = content.split("\n")
        in_model = None
        model_fields = []
        model_start_line = 0

        for idx, line in enumerate(lines, start=1):
            model_match = re.match(r"^model\s+([A-Za-z0-9_]+)\s*\{", line.strip())
            if model_match:
                in_model = model_match.group(1)
                model_fields = []
                model_start_line = idx
                continue
            if in_model:
                if line.strip() == "}":
                    facts.append({
                        "name": f"Prisma Model: {in_model}",
                        "evidence": f"{rel_path}:{model_start_line}",
                        "confidence": "high",
                        "details": model_fields[:12]
                    })
                    in_model = None
                else:
                    field_str = line.strip()
                    if field_str and not field_str.startswith("//"):
                        model_fields.append(field_str)

    # 3. TypeScript Interfaces / Types & Storage Keys & Signals
    ts_js_files = find_files(root, {".ts", ".tsx", ".js", ".jsx"})
    for rel_path in ts_js_files:
        content = read_source_file(root, rel_path)
        if not content:
            continue
        lines = content.split("\n")
        has_relevant = False

        # Check local constants for storage keys
        local_consts = {}
        for line in lines:
            m_const = re.match(r"^\s*(?:export\s+)?const\s+([A-Za-z0-9_]+)\s*=\s*['\"]([^'\"]+)['\"]", line)
            if m_const:
                local_consts[m_const.group(1)] = m_const.group(2)

        in_iface = None
        iface_fields = []
        iface_start = 0

        for idx, line in enumerate(lines, start=1):
            # Exported interface or type
            iface_match = re.match(r"^\s*export\s+(?:interface|type)\s+([A-Za-z0-9_]+)", line)
            if iface_match and not in_iface:
                in_iface = iface_match.group(1)
                iface_fields = []
                iface_start = idx
                has_relevant = True
                continue

            if in_iface:
                stripped = line.strip()
                if (stripped.endswith("}") or stripped.endswith("};")) and not stripped.startswith("{"):
                    facts.append({
                        "name": f"Type/Interface: {in_iface}",
                        "evidence": f"{rel_path}:{iface_start}",
                        "confidence": "high",
                        "details": iface_fields[:12]
                    })
                    in_iface = None
                else:
                    if stripped and not stripped.startswith("//") and not stripped.startswith("/*"):
                        iface_fields.append(stripped)

            # Schema libraries: Zod, Yup, Joi
            zod_match = re.search(r"(?:export\s+)?(?:const|let)\s+([A-Za-z0-9_]+)\s*=\s*(?:z|yup|Joi)\.object\(", line)
            if zod_match:
                s_name = zod_match.group(1)
                facts.append({
                    "name": f"Schema: {s_name}",
                    "evidence": f"{rel_path}:{idx}",
                    "confidence": "high",
                    "details": [line.strip()[:100]]
                })
                has_relevant = True

            # Storage keys
            storage_match = re.search(r"(?:localStorage|sessionStorage)\.(?:getItem|setItem|removeItem)\(\s*['\"]([^'\"]+)['\"]", line)
            if storage_match:
                key_name = storage_match.group(1)
                facts.append({
                    "name": f"Storage Key: {key_name}",
                    "evidence": f"{rel_path}:{idx}",
                    "confidence": "high",
                    "details": [line.strip()[:100]]
                })
                has_relevant = True
            else:
                c_match = re.search(r"(?:localStorage|sessionStorage)\.(?:getItem|setItem|removeItem)\(\s*([A-Za-z0-9_]+)", line)
                if c_match and c_match.group(1) in local_consts:
                    resolved_key = local_consts[c_match.group(1)]
                    facts.append({
                        "name": f"Storage Key: {resolved_key}",
                        "evidence": f"{rel_path}:{idx}",
                        "confidence": "high",
                        "details": [f"Constant {c_match.group(1)} resolves to '{resolved_key}'"]
                    })
                    has_relevant = True

            # IndexedDB
            idb_match = re.search(r"indexedDB\.open\(\s*['\"]([^'\"]+)['\"]", line)
            if idb_match:
                db_name = idb_match.group(1)
                facts.append({
                    "name": f"IndexedDB: {db_name}",
                    "evidence": f"{rel_path}:{idx}",
                    "confidence": "high",
                    "details": [line.strip()[:100]]
                })
                has_relevant = True

            # Signals: Time and money
            if "Date.now" in line or "toISOString" in line:
                signals.append({
                    "name": "Time serialization signal",
                    "evidence": f"{rel_path}:{idx}",
                    "detail": line.strip()[:100]
                })
                has_relevant = True
            if re.search(r"\b(?:cents|amount_cents|price_cents|in_cents)\b", line, re.IGNORECASE):
                signals.append({
                    "name": "Money representation signal (integer cents)",
                    "evidence": f"{rel_path}:{idx}",
                    "detail": line.strip()[:100]
                })
                candidates.append({
                    "id": f"data-cents-{len(candidates) + 1}",
                    "area": "data",
                    "rule": "Store monetary amounts as integer cents.",
                    "evidence": f"{rel_path}:{idx}"
                })
                has_relevant = True

        if has_relevant:
            sources.add(rel_path)

    # Sort facts deterministically
    facts.sort(key=lambda x: (x["name"], x["evidence"]))
    signals.sort(key=lambda x: (x["name"], x["evidence"]))

    return {
        "facts": facts,
        "signals": signals,
        "candidates": candidates,
        "sources": sorted(sources),
        "unsupported": []
    }


def render(data: dict) -> str:
    """Render extracted data facts to markdown format."""
    lines = ["# Data Blueprint\n"]
    lines.append("Extracted database schemas, models, schemas, and storage keys.\n")

    lines.append("## Generated facts\n")
    if not data["facts"]:
        lines.append("- No database models or storage keys detected.\n")
    else:
        for f in data["facts"]:
            lines.append(f"- **{f['name']}**")
            lines.append(f"  - Evidence: `{f['evidence']}` (confidence: {f['confidence']})")
            if f.get("details"):
                for d in f["details"][:10]:
                    lines.append(f"    - `{d}`")

    if data.get("signals"):
        lines.append("\n## Signals (evidence only, not facts)\n")
        for s in data["signals"]:
            lines.append(f"- {s['name']}: `{s['evidence']}` (`{s['detail']}`)")

    return "\n".join(lines).strip() + "\n"
