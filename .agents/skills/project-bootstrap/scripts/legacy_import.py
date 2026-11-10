#!/usr/bin/env python3
"""Legacy parity importer for Build Forge.

Inventories rules, tokens, schemas, and notes from existing agent files
(such as AGENTS.md, instructions in .cursor/rules, .claude/skills, or
custom agent files) so no existing rule is lost when Build Forge is adopted.

Commands:
  inventory [--root .]
  batch --area A [--root .] [--limit 15]
  apply --accept L001,L002 --drop L010 [--reason "..."] [--root .]
  status [--root .]
"""
import argparse
import difflib
import fnmatch
import hashlib
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

IGNORE_DIRS = {
    "node_modules", "dist", "build", ".git", ".next", ".nuxt", "coverage",
    ".venv", "venv", "__pycache__", ".turbo", ".vercel", ".netlify", "target", "out"
}

def write_text_lf(path: Path, content: str) -> None:
    """Write text file with strictly LF line endings across all operating systems."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content.replace("\r\n", "\n"))


# Documented thresholds for legacy import source classification
THIRD_PARTY_SIGNAL_THRESHOLD = 2
THIRD_PARTY_FRONTMATTER_KEYS = {
    "license", "metadata", "source", "author", "vendor", "repository", "homepage"
}
SCRIPT_EXTENSIONS = {
    ".sh", ".bash", ".py", ".js", ".mjs", ".cjs", ".ts", ".rb", ".pl", ".php", ".bin"
}
TEST_DIR_NAMES = {"test", "tests", "__tests__", "fixtures"}
GENERATOR_BANNER_SNIPPET = "by project-bootstrap"
GENERATOR_STAMP_MARKER = "<!-- build-forge:generated"

# Documented threshold for matching an existing profile rule:
# Token overlap (Jaccard similarity of lowercase word tokens) >= 0.50 AND
# difflib SequenceMatcher ratio >= 0.55, OR difflib ratio >= 0.72.
SIMILARITY_TOKEN_OVERLAP_MIN = 0.50
SIMILARITY_DIFFLIB_MIN = 0.55
SIMILARITY_DIFFLIB_DIRECT = 0.72

IMPERATIVE_WORDS = {
    "must", "never", "always", "do not", "dont", "don't", "only", "at least",
    "no more than", "ensure", "require", "shall", "cannot", "should not",
    "strictly", "forbidden", "prohibited", "avoid"
}

IMPERATIVE_STARTS = (
    "use ", "run ", "do ", "never ", "always ", "keep ", "follow ", "avoid ",
    "prefix ", "write ", "ensure ", "enforce ", "prevent ", "verify ", "check "
)


def normalize_text(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def word_tokens(text: str) -> set:
    return set(normalize_text(text).split())


def similarity_score(t1: str, t2: str) -> tuple:
    s1 = normalize_text(t1)
    s2 = normalize_text(t2)
    if not s1 or not s2:
        return 0.0, 0.0
    tokens1 = set(s1.split())
    tokens2 = set(s2.split())
    overlap = len(tokens1 & tokens2) / max(1, len(tokens1 | tokens2))
    ratio = difflib.SequenceMatcher(None, s1, s2).ratio()
    return overlap, ratio


def is_covered_by_rule(text: str, profile_rules: list) -> tuple:
    for r in profile_rules:
        r_text = r.get("text", "")
        overlap, ratio = similarity_score(text, r_text)
        if (overlap >= SIMILARITY_TOKEN_OVERLAP_MIN and ratio >= SIMILARITY_DIFFLIB_MIN) or ratio >= SIMILARITY_DIFFLIB_DIRECT:
            return True, r.get("id", "rule")
    return False, ""


def compute_file_hash(file_path: Path) -> str:
    try:
        content = file_path.read_bytes().replace(b"\r\n", b"\n")
        return hashlib.sha256(content).hexdigest()
    except Exception:
        return ""


def compute_dir_hashes(dir_path: Path) -> dict:
    hashes = {}
    if not dir_path.is_dir():
        return hashes
    for root, dirnames, files in os.walk(dir_path):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and d != ".git"]
        for f in sorted(files):
            full = Path(root, f)
            rel = full.relative_to(dir_path).as_posix()
            hashes[rel] = compute_file_hash(full)
    return hashes


def get_build_forge_skill_names(root: Path) -> set:
    lock_f = root / ".agents" / "build-forge.lock.json"
    if lock_f.is_file():
        try:
            data = json.loads(lock_f.read_text(encoding="utf-8"))
            names = set()
            for k in data.keys():
                parts = k.split("/")
                if len(parts) >= 2 and parts[0] == "skills":
                    names.add(parts[1])
            if names:
                return names
        except Exception:
            pass
    # Fallback to package skills
    pkg_skills_dir = Path(__file__).resolve().parent.parent.parent.parent / "skills"
    if pkg_skills_dir.is_dir():
        return {d.name for d in pkg_skills_dir.iterdir() if d.is_dir()}
    return set()


def is_generated_file(p: Path) -> bool:
    if p.name == "AGENTS.generated.md":
        return True
    try:
        head = p.read_text(encoding="utf-8", errors="ignore")[:400]
        if GENERATOR_BANNER_SNIPPET in head or GENERATOR_STAMP_MARKER in head:
            return True
    except Exception:
        pass
    return False


def get_references_info(root: Path) -> tuple:
    refs_yaml = root / ".agents" / "references.yaml"
    ref_names = set()
    ref_paths = set()
    if refs_yaml.is_file():
        try:
            data = yaml.safe_load(refs_yaml.read_text(encoding="utf-8")) or {}
            for r in data.get("references", []):
                if isinstance(r, dict):
                    if r.get("name"):
                        ref_names.add(r["name"])
                    if r.get("path"):
                        rp = Path(r["path"]).as_posix().strip()
                        while rp.startswith("./"):
                            rp = rp[2:].strip()
                        ref_paths.add(rp)
        except Exception:
            pass
    return ref_names, ref_paths


def detect_third_party_signals(skill_dir: Path) -> list:
    signals = []
    skill_md = skill_dir / "SKILL.md"
    if skill_md.is_file():
        try:
            content = skill_md.read_text(encoding="utf-8", errors="ignore")
            m = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if m:
                fm = yaml.safe_load(m.group(1)) or {}
                if isinstance(fm, dict):
                    found_keys = [k for k in fm if k.lower() in THIRD_PARTY_FRONTMATTER_KEYS]
                    if found_keys:
                        signals.append(f"frontmatter keys: {', '.join(sorted(found_keys))}")
        except Exception:
            pass

    non_doc_files = []
    has_test_folder = False
    has_license = False
    has_git = False

    try:
        for item in skill_dir.iterdir():
            if item.is_file():
                nl = item.name.lower()
                if nl.startswith("license"):
                    has_license = True
                elif nl == "package.json" or nl.endswith(".schema.json"):
                    non_doc_files.append(item.name)
                elif item.suffix.lower() in SCRIPT_EXTENSIONS:
                    non_doc_files.append(item.name)
            elif item.is_dir():
                nl = item.name.lower()
                if nl in TEST_DIR_NAMES:
                    has_test_folder = True
                elif nl == ".git":
                    has_git = True
                if nl in ("scripts", "bin", "src"):
                    for sub in item.rglob("*"):
                        if sub.is_file() and sub.suffix.lower() in SCRIPT_EXTENSIONS:
                            non_doc_files.append(f"{nl}/{sub.name}")
                            break
    except Exception:
        pass

    if non_doc_files:
        signals.append(f"non document files: {', '.join(non_doc_files[:3])}")
    if has_license:
        signals.append("LICENSE file present")
    if has_git:
        signals.append(".git folder present")
    if has_test_folder:
        signals.append("test folder present")

    return signals


def should_ignore_file(file_path: Path, skill_dir: Path) -> bool:
    try:
        rel = file_path.relative_to(skill_dir)
        parts = rel.parts
        # Never ignore a references/ folder inside a local skill
        if "references" in parts:
            return False
        for p in parts[:-1]:
            if p.lower() in TEST_DIR_NAMES:
                return True
        fname = file_path.name.lower()
        if fnmatch.fnmatch(fname, "*.test.*") or fnmatch.fnmatch(fname, "*.spec.*"):
            return True
    except Exception:
        pass
    return False


def classify_skill_folder(d: Path, root: Path, bf_skills: set, ref_names: set, ref_paths: set) -> dict:
    name = d.name
    vendor_dir = root / ".agents" / "vendor" / name

    # 1. build-forge
    if name in bf_skills:
        return {"class": "build-forge", "reason": "Build Forge pipeline skill", "diff_files": []}

    # 2. generated convention skills
    skill_md = d / "SKILL.md"
    if skill_md.is_file() and is_generated_file(skill_md):
        return {"class": "generated", "reason": "Generated convention skill", "diff_files": []}

    # 3. reference (direct reference match)
    rel_posix = d.relative_to(root).as_posix()
    if name in ref_names or rel_posix in ref_paths:
        if vendor_dir.is_dir():
            s_hashes = compute_dir_hashes(d)
            v_hashes = compute_dir_hashes(vendor_dir)
            if s_hashes == v_hashes:
                return {
                    "class": "vendor-dup",
                    "reason": f"Identical to vendor copy (.agents/vendor/{name}). Propose refs.py dedupe.",
                    "diff_files": []
                }
            else:
                diff_files = [f for f in sorted(set(s_hashes.keys()) | set(v_hashes.keys())) if s_hashes.get(f) != v_hashes.get(f)]
                return {
                    "class": "modified-fork",
                    "reason": f"{len(diff_files)} file(s) differ from vendor copy (.agents/vendor/{name})",
                    "diff_files": diff_files
                }
        return {"class": "reference", "reason": "Matches entry in .agents/references.yaml", "diff_files": []}

    # 4. vendor-dup without reference entry (name matches vendor folder)
    if vendor_dir.is_dir():
        s_hashes = compute_dir_hashes(d)
        v_hashes = compute_dir_hashes(vendor_dir)
        if s_hashes == v_hashes:
            return {
                "class": "vendor-dup",
                "reason": f"Identical to vendor copy (.agents/vendor/{name}). Propose refs.py dedupe.",
                "diff_files": []
            }
        else:
            diff_files = [f for f in sorted(set(s_hashes.keys()) | set(v_hashes.keys())) if s_hashes.get(f) != v_hashes.get(f)]
            return {
                "class": "modified-fork",
                "reason": f"{len(diff_files)} file(s) differ from vendor copy (.agents/vendor/{name})",
                "diff_files": diff_files
            }

    # 5. likely-third-party (2 or more signals)
    signals = detect_third_party_signals(d)
    if len(signals) >= THIRD_PARTY_SIGNAL_THRESHOLD:
        return {
            "class": "likely-third-party",
            "reason": f"Matched {len(signals)} signals: {'; '.join(signals)}",
            "signals": signals,
            "diff_files": []
        }

    # 6. local
    return {"class": "local", "reason": "Local skill", "diff_files": []}


def find_and_classify_sources(root: Path, include_skipped: bool = False):
    bf_skills = get_build_forge_skill_names(root)
    ref_names, ref_paths = get_references_info(root)

    active_files = []
    skipped_sources = []
    decision_sources = []
    source_counts = {
        "local": 0, "modified-fork": 0, "vendor-dup": 0,
        "likely-third-party": 0, "build-forge": 0, "generated": 0, "reference": 0,
        "needs-decision": 0
    }

    def count_stmts(p: Path) -> int:
        return len(split_statements(p, root))

    # 1. Root agent files
    for name in ("AGENTS.md", "CLAUDE.md", ".cursorrules", "INSTRUCTIONS.md", ".windsurfrules", ".clinerules"):
        p = root / name
        if p.is_file():
            if is_generated_file(p):
                cnt = count_stmts(p)
                source_counts["generated"] += cnt
                skipped_sources.append({
                    "path": name, "class": "generated",
                    "reason": "Generated router file", "count": cnt
                })
                if include_skipped:
                    active_files.append((p, "generated", "Generated router file"))
            else:
                active_files.append((p, "local", "Local root instruction file"))
                source_counts["local"] += count_stmts(p)

    gh_copilot = root / ".github" / "copilot-instructions.md"
    if gh_copilot.is_file():
        active_files.append((gh_copilot, "local", "GitHub Copilot instructions"))
        source_counts["local"] += count_stmts(gh_copilot)

    # 2. .cursor/rules
    cursor_rules = root / ".cursor" / "rules"
    if cursor_rules.is_dir():
        for p in sorted(cursor_rules.rglob("*")):
            if p.is_file() and p.suffix.lower() in (".md", ".mdc", ".txt"):
                if not should_ignore_file(p, cursor_rules):
                    active_files.append((p, "local", "Cursor rule"))
                    source_counts["local"] += count_stmts(p)

    # 3. .claude/skills
    claude_skills = root / ".claude" / "skills"
    if claude_skills.is_dir():
        for item in sorted(claude_skills.iterdir()):
            if item.is_symlink():
                continue
            if item.is_dir():
                for p in sorted(item.rglob("*")):
                    if p.is_file() and p.suffix.lower() in (".md", ".txt"):
                        if not should_ignore_file(p, item):
                            active_files.append((p, "local", "Claude skill"))
                            source_counts["local"] += count_stmts(p)

    # 4. .agents/vendor (always reference, never legacy source)
    vendor_dir = root / ".agents" / "vendor"
    if vendor_dir.is_dir():
        for vd in sorted(vendor_dir.iterdir()):
            if not vd.is_dir() or vd.name.startswith("."):
                continue
            v_cnt = 0
            v_files = []
            for p in sorted(vd.rglob("*")):
                if p.is_file() and p.suffix.lower() in (".md", ".txt"):
                    if not should_ignore_file(p, vd):
                        v_cnt += count_stmts(p)
                        v_files.append(p)
            source_counts["reference"] += v_cnt
            skipped_sources.append({
                "path": f".agents/vendor/{vd.name}",
                "class": "reference",
                "reason": "Installed vendor reference",
                "count": v_cnt
            })
            if include_skipped:
                for vf in v_files:
                    active_files.append((vf, "reference", "Vendor reference"))

    # 5. .agents/skills
    skills_dir = root / ".agents" / "skills"
    if skills_dir.is_dir():
        candidate_folders = []
        for item in sorted(skills_dir.iterdir()):
            if not item.is_dir() or item.name.startswith("."):
                continue
            c_info = classify_skill_folder(item, root, bf_skills, ref_names, ref_paths)
            s_class = c_info["class"]

            skill_files = []
            for p in sorted(item.rglob("*")):
                if p.is_file() and p.suffix.lower() in (".md", ".txt"):
                    if not should_ignore_file(p, item):
                        skill_files.append(p)

            s_cnt = sum(count_stmts(sf) for sf in skill_files)
            candidate_folders.append({
                "item": item,
                "c_info": c_info,
                "s_class": s_class,
                "skill_files": skill_files,
                "s_cnt": s_cnt
            })

        # Calculate candidate statements across non-build-forge/non-reference folders
        total_candidate_stmts = sum(
            cf["s_cnt"] for cf in candidate_folders
            if cf["s_class"] not in ("build-forge", "generated", "reference", "vendor-dup")
        )

        for cf in candidate_folders:
            item = cf["item"]
            c_info = cf["c_info"]
            s_class = cf["s_class"]
            reason = c_info["reason"]
            diff_files = set(c_info.get("diff_files", []))
            skill_files = cf["skill_files"]
            s_cnt = cf["s_cnt"]

            # Volume guard: if 1 source folder produces > 100 statements, or > 40% of all statements, mark needs-decision
            is_volume_tripped = False
            if s_class not in ("build-forge", "generated", "reference", "vendor-dup"):
                if s_cnt > 100:
                    is_volume_tripped = True
                elif len(candidate_folders) > 1 and total_candidate_stmts > 50 and s_cnt > 10 and (s_cnt / total_candidate_stmts) > 0.40:
                    is_volume_tripped = True

            if is_volume_tripped:
                s_class = "needs-decision"
                guard_msg = f"{s_cnt} statements from .agents/skills/{item.name} look like reference or third party content"
                source_counts["needs-decision"] += s_cnt
                decision_sources.append({
                    "path": f".agents/skills/{item.name}",
                    "class": "needs-decision",
                    "signals": f"{s_cnt} statements (> volume threshold)",
                    "proposed_action": guard_msg
                })
                skipped_sources.append({
                    "path": f".agents/skills/{item.name}",
                    "class": "needs-decision",
                    "reason": guard_msg,
                    "count": s_cnt
                })
                print(f"Warning: {guard_msg}")
                if include_skipped:
                    for sf in skill_files:
                        active_files.append((sf, "needs-decision", guard_msg))
                continue

            if s_class == "local":
                for sf in skill_files:
                    active_files.append((sf, "local", "Local skill"))
                    source_counts["local"] += count_stmts(sf)
            elif s_class == "modified-fork":
                mod_count = 0
                skip_count = 0
                for sf in skill_files:
                    rel_in_skill = sf.relative_to(item).as_posix()
                    if rel_in_skill in diff_files:
                        active_files.append((sf, "modified-fork", f"Modified fork ({rel_in_skill})"))
                        mod_count += count_stmts(sf)
                    else:
                        skip_count += count_stmts(sf)
                source_counts["modified-fork"] += mod_count
                source_counts["vendor-dup"] += skip_count
                decision_sources.append({
                    "path": f".agents/skills/{item.name}",
                    "class": "modified-fork",
                    "signals": f"{len(diff_files)} file(s) differ from vendor copy",
                    "proposed_action": "Review diff and reconcile with vendor reference"
                })
                if skip_count > 0:
                    skipped_sources.append({
                        "path": f".agents/skills/{item.name} (unmodified files)",
                        "class": "vendor-dup",
                        "reason": "Unmodified files identical to vendor copy",
                        "count": skip_count
                    })
            else:
                source_counts[s_class] += s_cnt
                skipped_sources.append({
                    "path": f".agents/skills/{item.name}",
                    "class": s_class,
                    "reason": reason,
                    "count": s_cnt
                })
                if s_class == "likely-third-party":
                    decision_sources.append({
                        "path": f".agents/skills/{item.name}",
                        "class": "likely-third-party",
                        "signals": "; ".join(c_info.get("signals", [])),
                        "proposed_action": "Register as reference or keep as local skill"
                    })
                if include_skipped:
                    for sf in skill_files:
                        active_files.append((sf, s_class, reason))

    return active_files, skipped_sources, decision_sources, source_counts


def find_legacy_files(root: Path) -> list:
    """Compatibility wrapper returning unique active local/modified file paths."""
    active_files, _, _, _ = find_and_classify_sources(root, include_skipped=False)
    seen = set()
    unique = []
    for f, _, _ in active_files:
        resolved = f.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(f)
    return unique


def split_statements(file_path: Path, root: Path) -> list:
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    lines = content.splitlines()
    statements = []
    rel_path = file_path.relative_to(root).as_posix()

    in_code_block = False
    code_start_line = 0
    code_lines = []

    in_table = False
    table_start_line = 0
    table_lines = []

    current_bullet_line = 0
    current_bullet_lines = []

    current_heading = ""
    current_heading_line = 0
    current_paragraph_lines = []

    def flush_table():
        nonlocal in_table, table_start_line, table_lines
        if table_lines:
            if len(table_lines) > 10:
                # Table longer than 10 lines routes as 1 unit
                table_text = "\n".join(table_lines).strip()
                statements.append({
                    "file": rel_path,
                    "line": table_start_line,
                    "text": table_text,
                    "raw": "\n".join(table_lines)
                })
            else:
                for i, tline in enumerate(table_lines):
                    s_t = tline.strip()
                    if i == 0 or re.match(r"^\|(\s*:?-+:?\s*\|)+$", s_t):
                        continue
                    statements.append({
                        "file": rel_path,
                        "line": table_start_line + i,
                        "text": s_t,
                        "raw": s_t
                    })
            table_lines = []
            in_table = False

    def flush_bullet():
        nonlocal current_bullet_line, current_bullet_lines
        if current_bullet_lines:
            text = " ".join(s.strip() for s in current_bullet_lines).strip()
            if text:
                statements.append({
                    "file": rel_path,
                    "line": current_bullet_line,
                    "text": text,
                    "raw": "\n".join(current_bullet_lines)
                })
            current_bullet_lines = []
            current_bullet_line = 0

    def flush_paragraph():
        nonlocal current_heading_line, current_heading, current_paragraph_lines
        if current_paragraph_lines:
            text = " ".join(s.strip() for s in current_paragraph_lines).strip()
            if text:
                full_text = f"{current_heading}: {text}" if current_heading else text
                statements.append({
                    "file": rel_path,
                    "line": current_heading_line or 1,
                    "text": full_text,
                    "raw": "\n".join(current_paragraph_lines)
                })
            current_paragraph_lines = []

    for idx, line in enumerate(lines, 1):
        stripped = line.strip()

        # Handle fenced code blocks
        if stripped.startswith("```"):
            flush_bullet()
            flush_paragraph()
            flush_table()
            if not in_code_block:
                in_code_block = True
                code_start_line = idx
                code_lines = [line]
            else:
                code_lines.append(line)
                in_code_block = False
                statements.append({
                    "file": rel_path,
                    "line": code_start_line,
                    "text": "\n".join(code_lines).strip(),
                    "raw": "\n".join(code_lines)
                })
                code_lines = []
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        # Handle tables
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_bullet()
            flush_paragraph()
            if not in_table:
                in_table = True
                table_start_line = idx
                table_lines = [line]
            else:
                table_lines.append(line)
            continue
        elif in_table:
            flush_table()

        # Handle headings
        if stripped.startswith("#"):
            flush_bullet()
            flush_paragraph()
            current_heading = stripped.lstrip("#").strip()
            current_heading_line = idx
            continue

        # Handle bullet lists: - , * , +
        bullet_match = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
        if bullet_match:
            flush_bullet()
            flush_paragraph()
            current_bullet_line = idx
            current_bullet_lines = [bullet_match.group(2)]
            continue

        # Handle numbered lists: 1. , 2.
        num_match = re.match(r"^(\s*)\d+[\.\)]\s+(.*)$", line)
        if num_match:
            flush_bullet()
            flush_paragraph()
            current_bullet_line = idx
            current_bullet_lines = [num_match.group(2)]
            continue

        # Handle blank lines
        if not stripped:
            flush_bullet()
            flush_paragraph()
            continue

        # Continuation line for bullet or new paragraph line
        if current_bullet_lines:
            current_bullet_lines.append(stripped)
        else:
            if not current_paragraph_lines:
                current_heading_line = idx
            current_paragraph_lines.append(stripped)

    flush_bullet()
    flush_paragraph()
    flush_table()

    return statements


def infer_area(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ("token", "color", "palette", "font", "theme", "spacing", "radius")):
        return "tokens"
    if any(k in t for k in ("button", "dialog", "modal", "toast", "spinner", "screen", "component", "aria", "icon", "ui")):
        return "design"
    if any(k in t for k in ("breakpoint", "mobile", "desktop", "responsive", "layout", "width", "touch")):
        return "responsive"
    if any(k in t for k in ("database", "table", "sql", "prisma", "storage", "schema", "query", "model", "localstorage")):
        return "data"
    if any(k in t for k in ("folder", "directory", "layer", "file placement", "root")):
        return "structure"
    if any(k in t for k in ("naming", "pascalcase", "camelcase", "kebab-case", "snake_case", "prefix", "suffix", "case")):
        return "naming"
    if any(k in t for k in ("commit", "branch", "pr", "merge", "git")):
        return "git"
    if any(k in t for k in ("auth", "password", "secret", "token", "permission", "role", "credential", "security")):
        return "security"
    if any(k in t for k in ("test", "lint", "verify", "check", "assert")):
        return "verify"
    return "process"


def classify_statement(stmt: dict, seen_statements: list, profile_rules: list, blueprints: dict) -> dict:
    text = stmt["text"]
    t_lower = text.lower()

    # 1. Check duplicate against seen statements
    for prev in seen_statements:
        ov, rat = similarity_score(text, prev["text"])
        if (ov >= 0.85 and rat >= 0.85) or rat >= 0.90:
            return {
                "class": "duplicate",
                "proposed_destination": f"duplicate of {prev['id']}",
                "status": "dropped",
                "reason": f"duplicate of {prev['id']}"
            }

    # 2. Check covered by existing profile rule
    covered, rule_id = is_covered_by_rule(text, profile_rules)
    if covered:
        return {
            "class": "covered",
            "proposed_destination": f"profile rule [{rule_id}]",
            "status": "covered",
            "reason": f"matches profile rule {rule_id}"
        }

    # 3. Check derivable
    # 3a. derivable-tokens
    if re.search(r"--[a-zA-Z][a-zA-Z0-9_-]*", text) or ":root" in t_lower or "@theme" in t_lower or re.search(r"#[0-9a-fA-F]{3,8}\b", text) or any(k in t_lower for k in ("color palette", "design tokens", "spacing tokens")):
        status = "pending"
        matched_fact = ""
        if blueprints and "tokens" in blueprints:
            # Check token name match
            token_matches = re.findall(r"(--[a-zA-Z0-9_-]+)", text)
            for tm in token_matches:
                if tm in blueprints["tokens"]:
                    status = "covered"
                    matched_fact = tm
                    break
        return {
            "class": "derivable-tokens",
            "proposed_destination": ".agents/blueprints/tokens.md",
            "status": status,
            "reason": f"matched blueprint token {matched_fact}" if matched_fact else ""
        }

    # 3b. derivable-data
    if any(k in text for k in ("CREATE TABLE", "ALTER TABLE", "PRIMARY KEY", "FOREIGN KEY", "localStorage.", "sessionStorage.", "model ", "enum ")) or re.search(r"(?:interface|type)\s+[A-Z]\w+", text):
        status = "pending"
        matched_fact = ""
        if blueprints and "data" in blueprints:
            table_matches = re.findall(r"(?:model|TABLE|interface|type)\s+([A-Za-z0-9_]+)", text, re.IGNORECASE)
            for tm in table_matches:
                if tm.lower() in blueprints["data"].lower():
                    status = "covered"
                    matched_fact = tm
                    break
        return {
            "class": "derivable-data",
            "proposed_destination": ".agents/blueprints/data.md",
            "status": status,
            "reason": f"matched blueprint data model {matched_fact}" if matched_fact else ""
        }

    # 3c. derivable-layout
    if any(k in t_lower for k in ("@media", "breakpoint", "touch target", "safe-area-inset", "min-width", "max-width")) or re.search(r"\b\d+px\b", text):
        if any(b in text for b in ("sm:", "md:", "lg:", "xl:", "2xl:")) or "breakpoint" in t_lower:
            status = "pending"
            matched_fact = ""
            if blueprints and "layout" in blueprints:
                bp_matches = re.findall(r"(\d+px)", text)
                for bm in bp_matches:
                    if bm in blueprints["layout"]:
                        status = "covered"
                        matched_fact = bm
                        break
            return {
                "class": "derivable-layout",
                "proposed_destination": ".agents/blueprints/layout.md",
                "status": status,
                "reason": f"matched blueprint layout {matched_fact}" if matched_fact else ""
            }

    # 3d. derivable-ui
    if any(k in t_lower for k in ("component catalog", "exported components", "ui primitives", "props table", "interface table", "prop | type", "interface | type")):
        status = "pending"
        matched_fact = ""
        if blueprints and "ui" in blueprints:
            comp_matches = re.findall(r"<([A-Z][a-zA-Z0-9]+)", text)
            for cm in comp_matches:
                if cm in blueprints["ui"]:
                    status = "covered"
                    matched_fact = cm
                    break
        return {
            "class": "derivable-ui",
            "proposed_destination": ".agents/blueprints/ui.md",
            "status": status,
            "reason": f"matched blueprint ui component {matched_fact}" if matched_fact else ""
        }

    # 4. Check rule-candidate (imperative statement)
    is_imperative = any(re.search(rf"\b{re.escape(w)}\b", t_lower) for w in IMPERATIVE_WORDS)
    if not is_imperative:
        is_imperative = any(t_lower.startswith(prefix) for prefix in IMPERATIVE_STARTS)

    area = infer_area(text)
    if is_imperative:
        return {
            "class": "rule-candidate",
            "proposed_destination": f"profile rule [area: {area}]",
            "status": "pending",
            "reason": ""
        }

    # 5. Note (explanation or rationale)
    return {
        "class": "note",
        "proposed_destination": f".agents/notes/{area}.md",
        "status": "pending",
        "reason": ""
    }


def load_blueprints(root: Path) -> dict:
    bp_dir = root / ".agents" / "blueprints"
    if not bp_dir.is_dir():
        return {}
    blueprints = {}
    for p in sorted(bp_dir.glob("*.md")):
        area = p.stem.split("-")[0].lower()
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            blueprints[area] = blueprints.get(area, "") + "\n" + content
        except Exception:
            pass
    return blueprints


def load_profile_rules(root: Path) -> tuple:
    prof_path = root / ".agents" / "project-profile.yaml"
    if not prof_path.is_file():
        return None, []
    try:
        prof = yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {}
        return prof, prof.get("rules", []) or []
    except Exception:
        return None, []


def calculate_coverage(statements: list) -> tuple:
    relevant = [s for s in statements if s["class"] in (
        "rule-candidate", "derivable-data", "derivable-tokens", "derivable-ui", "derivable-layout"
    )]
    covered_or_accepted = [s for s in relevant if s["status"] in ("covered", "accepted", "routed")]
    if not relevant:
        return 100.0, 0, 0
    ratio = len(covered_or_accepted) / len(relevant)
    return round(ratio * 100, 1), len(covered_or_accepted), len(relevant)


def escape_table_cell(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\n", "<br>").replace("|", "\\|")
    return cleaned.strip()


def unescape_table_cell(text: str) -> str:
    return text.replace("\\|", "|").replace("<br>", "\n").strip()


def split_table_row(line: str) -> list:
    stripped = line.strip()
    if stripped.startswith("|") and stripped.endswith("|"):
        stripped = stripped[1:-1]
    tokens = re.findall(r"(?:\\\||[^|])+", stripped)
    return [t.strip() for t in tokens]


def extract_section(content: str, header: str) -> str:
    idx = content.find(header)
    if idx == -1:
        return ""
    start = idx + len(header)
    next_idx = content.find("\n## ", start)
    if next_idx == -1:
        return content[start:].strip()
    return content[start:next_idx].strip()


def read_ledger_decision_sources(ledger_path: Path) -> list:
    if not ledger_path.is_file():
        return []
    try:
        text = ledger_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    sec = extract_section(text, "## Needs a Decision")
    if not sec or "_No sources needing decision._" in sec:
        return []
    decision_sources = []
    for line in sec.splitlines():
        line = line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        if re.match(r"^\|(\s*:?-+:?\s*\|)+$", line) or "| Source | Class |" in line:
            continue
        parts = split_table_row(line)
        if len(parts) >= 2:
            decision_sources.append({
                "path": unescape_table_cell(parts[0]),
                "class": unescape_table_cell(parts[1]),
                "signals": unescape_table_cell(parts[2]) if len(parts) > 2 else "",
                "proposed_action": unescape_table_cell(parts[3]) if len(parts) > 3 else ""
            })
    return decision_sources


def write_ledger(ledger_path: Path, statements: list, skipped_sources: list = None, decision_sources: list = None, source_counts: dict = None):
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    cov_pct, cov_count, rel_count = calculate_coverage(statements)

    counts_status = {"pending": 0, "covered": 0, "accepted": 0, "dropped": 0, "routed": 0}
    counts_class = {
        "covered": 0, "derivable-data": 0, "derivable-tokens": 0,
        "derivable-ui": 0, "derivable-layout": 0, "rule-candidate": 0,
        "note": 0, "duplicate": 0
    }

    for s in statements:
        st = s.get("status", "pending")
        counts_status[st] = counts_status.get(st, 0) + 1
        cl = s.get("class", "note")
        counts_class[cl] = counts_class.get(cl, 0) + 1

    existing_content = ""
    if ledger_path.is_file():
        try:
            existing_content = ledger_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass

    lines = [
        "# Legacy Parity Ledger",
        "",
        "Generated by legacy_import.py. Tracks legacy rules, tokens, schemas, and notes.",
        "",
        "## Summary",
        f"- Coverage: {cov_pct}% ({cov_count}/{rel_count} rule-candidate and derivable statements covered or accepted)",
        f"- Total statements: {len(statements)}",
        "- Status counts:",
        f"  - pending: {counts_status['pending']}",
        f"  - covered: {counts_status['covered']}",
        f"  - routed: {counts_status['routed']}",
        f"  - accepted: {counts_status['accepted']}",
        f"  - dropped: {counts_status['dropped']}",
        "",
        "## Statement Counts by Source Class"
    ]

    if source_counts is not None:
        for sc in ("local", "modified-fork", "vendor-dup", "likely-third-party", "build-forge", "generated", "reference"):
            lines.append(f"- {sc}: {source_counts.get(sc, 0)}")
    elif "## Statement Counts by Source Class" in existing_content:
        sec = extract_section(existing_content, "## Statement Counts by Source Class")
        if sec:
            lines.append(sec)
        else:
            lines.append("- local: 0")
    else:
        lines.append("- local: 0")

    lines.extend([
        "",
        "## Counts by Class",
        f"- covered: {counts_class['covered']}",
        f"- derivable-data: {counts_class['derivable-data']}",
        f"- derivable-tokens: {counts_class['derivable-tokens']}",
        f"- derivable-ui: {counts_class['derivable-ui']}",
        f"- derivable-layout: {counts_class['derivable-layout']}",
        f"- rule-candidate: {counts_class['rule-candidate']}",
        f"- note: {counts_class['note']}",
        f"- duplicate: {counts_class['duplicate']}",
        "",
        "## Skipped Sources"
    ])

    if skipped_sources is not None:
        if skipped_sources:
            lines.extend([
                "| Source | Class | Reason |",
                "|---|---|---|"
            ])
            for item in skipped_sources:
                lines.append(f"| {item['path']} | {item['class']} | {escape_table_cell(item['reason'])} |")
        else:
            lines.append("_No skipped sources._")
    elif "## Skipped Sources" in existing_content:
        sec = extract_section(existing_content, "## Skipped Sources")
        if sec:
            lines.append(sec)
        else:
            lines.append("_No skipped sources._")
    else:
        lines.append("_No skipped sources._")

    lines.extend([
        "",
        "## Needs a Decision"
    ])

    if decision_sources is not None:
        if decision_sources:
            lines.extend([
                "| Source | Class | Signals or Diff | Proposed Action |",
                "|---|---|---|---|"
            ])
            for item in decision_sources:
                lines.append(f"| {item['path']} | {item['class']} | {escape_table_cell(item['signals'])} | {escape_table_cell(item['proposed_action'])} |")
        else:
            lines.append("_No sources needing decision._")
    elif "## Needs a Decision" in existing_content:
        sec = extract_section(existing_content, "## Needs a Decision")
        if sec:
            lines.append(sec)
        else:
            lines.append("_No sources needing decision._")
    else:
        lines.append("_No sources needing decision._")

    lines.extend([
        "",
        "## Ledger",
        "| ID | Source | Class | Proposed Destination | Status | Details | Source Class |",
        "|---|---|---|---|---|---|---|"
    ])

    for s in statements:
        details = s.get("reason") or s.get("text", "")
        source_class = s.get("source_class", "local")
        row = f"| {s['id']} | {s['file']}:{s['line']} | {s['class']} | {s['proposed_destination']} | {s['status']} | {escape_table_cell(details)} | {source_class} |"
        lines.append(row)

    write_text_lf(ledger_path, "\n".join(lines) + "\n")


def read_ledger(ledger_path: Path) -> list:
    if not ledger_path.is_file():
        return []
    text = ledger_path.read_text(encoding="utf-8", errors="ignore")
    statements = []
    in_table = False

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("| ID | Source | Class |"):
            in_table = True
            continue
        if in_table:
            if re.match(r"^\|(\s*:?-+:?\s*\|)+$", line):
                continue
            if not line.startswith("|") or not line.endswith("|"):
                continue
            parts = split_table_row(line)
            if len(parts) >= 6:
                sid = parts[0]
                src = parts[1]
                sclass = parts[2]
                dest = parts[3]
                status = parts[4]
                details = unescape_table_cell(parts[5])
                source_class = parts[6] if len(parts) >= 7 else "local"

                file_part = src
                line_part = 1
                if ":" in src:
                    f_str, l_str = src.rsplit(":", 1)
                    file_part = f_str
                    try:
                        line_part = int(l_str)
                    except ValueError:
                        line_part = 1

                statements.append({
                    "id": sid,
                    "file": file_part,
                    "line": line_part,
                    "class": sclass,
                    "source_class": source_class,
                    "proposed_destination": dest,
                    "status": status,
                    "text": details,
                    "raw": details,
                    "reason": details if status in ("dropped", "covered", "routed") else ""
                })

    return statements


def cmd_inventory(root: Path, include_skipped: bool = False):
    active_files, skipped_sources, decision_sources, source_counts = find_and_classify_sources(root, include_skipped=include_skipped)
    profile_data, profile_rules = load_profile_rules(root)
    blueprints = load_blueprints(root)

    raw_statements = []
    for f, s_class, s_reason in active_files:
        stmts = split_statements(f, root)
        for st in stmts:
            st["source_class"] = s_class
        raw_statements.extend(stmts)

    # Process local statements first so duplicates from vendor/forks yield to local
    raw_statements.sort(key=lambda st: 0 if st.get("source_class") == "local" else 1)

    classified_statements = []
    counter = 1
    for raw in raw_statements:
        sid = f"L{counter:03d}"
        res = classify_statement(raw, classified_statements, profile_rules, blueprints)
        classified_statements.append({
            "id": sid,
            "file": raw["file"],
            "line": raw["line"],
            "text": raw["text"],
            "raw": raw["raw"],
            "class": res["class"],
            "source_class": raw.get("source_class", "local"),
            "proposed_destination": res["proposed_destination"],
            "status": res["status"],
            "reason": res.get("reason", "")
        })
        counter += 1

    ledger_path = root / ".agents" / "legacy-parity.md"
    write_ledger(
        ledger_path,
        classified_statements,
        skipped_sources=skipped_sources,
        decision_sources=decision_sources,
        source_counts=source_counts
    )

    cov_pct, cov_count, rel_count = calculate_coverage(classified_statements)
    counts_class = {}
    for s in classified_statements:
        c = s["class"]
        counts_class[c] = counts_class.get(c, 0) + 1

    print(f"Legacy parity inventory: {len(classified_statements)} statements across {len(active_files)} file(s).")
    for cl in ("covered", "derivable-data", "derivable-tokens", "derivable-ui", "derivable-layout", "rule-candidate", "note", "duplicate"):
        print(f"  {cl}: {counts_class.get(cl, 0)}")
    print(f"\nCoverage: {cov_pct}% ({cov_count}/{rel_count} rule-candidate and derivable statements covered or accepted).")
    print("\nStatement counts by source class:")
    for sc in ("local", "modified-fork", "vendor-dup", "likely-third-party", "build-forge", "generated", "reference"):
        print(f"  {sc}: {source_counts.get(sc, 0)}")
    if decision_sources:
        print(f"\nWarning: {len(decision_sources)} source(s) need a decision:")
        for ds in decision_sources:
            print(f"  - {ds['path']} ({ds['class']}): {ds['signals']}")
            print(f"    Proposed action: {ds['proposed_action']}")
    print(f"\nLedger written to {ledger_path.relative_to(root).as_posix()}.")


def resolve_blueprint_area_for_statement(stmt: dict) -> str:
    s_class = stmt.get("class", "")
    if s_class == "derivable-tokens":
        return "tokens"
    if s_class == "derivable-data":
        return "data"
    if s_class == "derivable-ui":
        return "ui"
    if s_class == "derivable-layout":
        return "layout"

    dest = stmt.get("proposed_destination", "").lower()
    for area in ("tokens", "data", "ui", "layout", "auth", "config"):
        if f"/{area}.md" in dest or f"area: {area}" in dest:
            return area
    inferred = infer_area(stmt.get("text", "")).lower()
    if inferred in ("tokens", "data", "ui", "layout", "auth", "config"):
        return inferred
    if inferred == "design":
        return "ui"
    if inferred == "responsive":
        return "layout"
    return "ui"


def find_evidence_anchor(root: Path, text: str) -> str:
    matches = re.findall(r"`?([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]{1,6})(?::(\d+))?`?", text)
    for path_str, line_str in matches:
        path_str = path_str.strip()
        if not path_str or path_str.startswith("http") or path_str.startswith(".git"):
            continue
        norm_path = path_str.replace("\\", "/")
        candidate = root / norm_path
        if candidate.is_file():
            line_no = line_str if line_str else "1"
            return f"{norm_path}:{line_no}"
    return ""


def ensure_blueprint_file(root: Path, area: str) -> Path:
    bp_dir = root / ".agents" / "blueprints"
    bp_dir.mkdir(parents=True, exist_ok=True)
    target = bp_dir / f"{area}.md"
    if not target.is_file():
        bp_script = None
        cand1 = root / ".agents" / "skills" / "project-blueprints" / "scripts" / "blueprint.py"
        cand2 = Path(__file__).resolve().parent.parent.parent / "project-blueprints" / "scripts" / "blueprint.py"
        if cand1.is_file():
            bp_script = cand1
        elif cand2.is_file():
            bp_script = cand2

        if bp_script:
            import subprocess
            subprocess.run([sys.executable, "-B", str(bp_script), "init", "--areas", area, "--root", str(root)], check=False)

        if not target.is_file():
            content = (
                f"# {area.title()} Blueprint\n\n"
                f"Canonical {area} facts and contracts.\n\n"
                "<!-- BEGIN CUSTOM: contracts -->\n"
                "<!-- END CUSTOM: contracts -->\n"
            )
            write_text_lf(target, content)

    idx_file = bp_dir / "index.md"
    if not idx_file.is_file():
        idx_lines = [
            "# Project Blueprints Index\n",
            "Deterministic, verified facts extracted directly from codebase evidence.\n",
            "## Areas",
            f"- [{area.title()} Blueprint]({area}.md)",
            ""
        ]
        write_text_lf(idx_file, "\n".join(idx_lines))
    else:
        try:
            c = idx_file.read_text(encoding="utf-8", errors="ignore")
            if f"{area}.md" not in c:
                write_text_lf(idx_file, c.rstrip() + f"\n- [{area.title()} Blueprint]({area}.md)\n")
        except Exception:
            pass

    return target


def route_statement_to_blueprint(root: Path, stmt: dict):
    area = resolve_blueprint_area_for_statement(stmt)
    target_file = ensure_blueprint_file(root, area)

    raw_text = stmt.get("raw") or stmt.get("text", "")
    evidence = find_evidence_anchor(root, raw_text)

    entry_lines = [f"- source: legacy {stmt['id']} {stmt['file']}:{stmt['line']}"]
    if evidence:
        entry_lines.append(f"  Evidence: {evidence}")
    entry_lines.append(raw_text)
    entry_str = "\n".join(entry_lines)

    content = target_file.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"(<!-- BEGIN CUSTOM:\s*contracts\s*-->)([\s\S]*?)(<!-- END CUSTOM:\s*contracts\s*-->)", content)
    if m:
        body = m.group(2).strip()
        if body:
            new_body = f"\n{body}\n\n{entry_str}\n"
        else:
            new_body = f"\n{entry_str}\n"
        new_content = content[:m.start(2)] + new_body + content[m.end(2):]
    else:
        new_content = content.rstrip() + f"\n\n<!-- BEGIN CUSTOM: contracts -->\n{entry_str}\n<!-- END CUSTOM: contracts -->\n"

    write_text_lf(target_file, new_content)

    stmt["status"] = "routed"
    stmt["reason"] = f"routed to .agents/blueprints/{area}.md (contracts)"
    stmt["proposed_destination"] = f".agents/blueprints/{area}.md"


def cmd_batch(root: Path, area: str, limit: int):
    ledger_path = root / ".agents" / "legacy-parity.md"
    if not ledger_path.is_file():
        sys.exit("Error: .agents/legacy-parity.md does not exist. Run inventory first.")

    statements = read_ledger(ledger_path)
    target_area = area.lower().strip()

    pending = []
    for s in statements:
        if s["status"] != "pending":
            continue
        dest = s["proposed_destination"].lower()
        s_area = infer_area(s["text"])
        if f"area: {target_area}" in dest or f"/{target_area}.md" in dest or s_area == target_area:
            pending.append(s)

    total_pending = len(pending)
    selected = pending[:limit]

    print(f"Pending statements for area '{area}': showing {len(selected)} of {total_pending} item(s).\n")
    for s in selected:
        print(f"--- Statement: {s['id']} ---")
        print(f"Source: {s['file']}:{s['line']}")
        print(f"Class:  {s['class']}")
        print(f"Text:   {s['text']}")
        if s["class"] == "rule-candidate":
            slug = re.sub(r"[^a-z0-9]+", "-", s["text"].lower()[:40]).strip("-") # strip-chars-ok: cleaning slug
            rule_id = f"{area}-{slug or s['id'].lower()}"
            print("Proposed Profile Rule:")
            print(f"  id: {rule_id}")
            print(f"  area: {area}")
            print(f"  text: \"{s['text']}\"")
            print("  enforced_by: manual")
            print("  evidence:")
            print(f"    - {s['file']}:{s['line']}")
        elif s["class"].startswith("derivable-"):
            bp_area = resolve_blueprint_area_for_statement(s)
            print(f"Proposed destination: .agents/blueprints/{bp_area}.md contracts ([{s['id']}] ({s['class']} -> {bp_area}.md))")
        else:
            print(f"Proposed destination: {s['proposed_destination']}")
        print()

    if total_pending > limit:
        print(f"{total_pending - limit} more pending statement(s) remain in area '{area}'.")


def cmd_apply(root: Path, accept_ids: list, drop_ids: list, route_ids: list, route_class: str, is_yes: bool, reason: str):
    ledger_path = root / ".agents" / "legacy-parity.md"
    if not ledger_path.is_file():
        sys.exit("Error: .agents/legacy-parity.md does not exist. Run inventory first.")

    statements = read_ledger(ledger_path)
    stmt_map = {s["id"]: s for s in statements}

    # Handle --route-class
    if route_class:
        target_class = route_class.strip().lower()
        pending_derivable = [
            s for s in statements
            if s.get("status") == "pending" and (
                (target_class == "derivable" and s.get("class", "").startswith("derivable-")) or
                s.get("class", "").lower() == target_class
            )
        ]
        if not is_yes:
            print(f"Pending derivable statements ({len(pending_derivable)}):")
            for s in pending_derivable:
                bp_area = resolve_blueprint_area_for_statement(s)
                first_line = (s.get("text", "")).splitlines()[0][:80]
                print(f"  [{s['id']}] ({s['class']} -> {bp_area}.md): {first_line}")
            print(f"\nPass --yes to route these {len(pending_derivable)} statement(s) into blueprint contracts.")
            return

        for s in pending_derivable:
            if s["id"] not in route_ids:
                route_ids.append(s["id"])

    prof_path = root / ".agents" / "project-profile.yaml"
    prof_data = None
    if prof_path.is_file():
        try:
            prof_data = yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            sys.exit(f"Error reading profile: {e}")

    accepted_rules_added = 0
    accepted_notes_added = 0
    dropped_count = 0
    routed_count = 0

    # 1. Process drops
    for sid in drop_ids:
        if sid in stmt_map:
            stmt = stmt_map[sid]
            stmt["status"] = "dropped"
            stmt["reason"] = reason or "Dropped by user"
            dropped_count += 1
        else:
            print(f"Warning: ID {sid} not found in ledger.")

    # 2. Process routes
    for sid in route_ids:
        if sid in stmt_map:
            stmt = stmt_map[sid]
            route_statement_to_blueprint(root, stmt)
            routed_count += 1
        else:
            print(f"Warning: ID {sid} not found in ledger.")

    # 3. Process accepts
    for sid in accept_ids:
        if sid not in stmt_map:
            print(f"Warning: ID {sid} not found in ledger.")
            continue
        stmt = stmt_map[sid]
        s_class = stmt["class"]
        area = infer_area(stmt["text"])
        m = re.search(r"area:\s*([a-zA-Z0-9_-]+)", stmt["proposed_destination"])
        if m:
            area = m.group(1)

        if s_class == "rule-candidate":
            stmt["status"] = "accepted"
            if prof_data is not None:
                slug = re.sub(r"[^a-z0-9]+", "-", stmt["text"].lower()[:40]).strip("-") # strip-chars-ok: cleaning slug
                rule_id = f"imported-{area}-{slug or sid.lower()}"
                rules = prof_data.setdefault("rules", [])
                existing_ids = {r.get("id") for r in rules if isinstance(r, dict)}
                if rule_id in existing_ids:
                    rule_id = f"imported-{area}-{sid.lower()}"

                rules.append({
                    "id": rule_id,
                    "area": area,
                    "text": stmt["text"],
                    "enforced_by": "manual",
                    "evidence": [f"{stmt['file']}:{stmt['line']}"]
                })
                accepted_rules_added += 1

        elif s_class == "note":
            stmt["status"] = "accepted"
            notes_dir = root / ".agents" / "notes"
            notes_dir.mkdir(parents=True, exist_ok=True)
            note_file = notes_dir / f"{area}.md"
            note_entry = f"- [{stmt['file']}:{stmt['line']}] {stmt['text']}\n"
            if not note_file.exists():
                write_text_lf(note_file, f"# Notes: {area}\n\n{note_entry}")
            else:
                with open(note_file, "a", encoding="utf-8", newline="\n") as nf:
                    nf.write(note_entry.replace("\r\n", "\n"))
            accepted_notes_added += 1

        elif s_class.startswith("derivable-"):
            stmt["status"] = "accepted"
            stmt["reason"] = "Accepted by user"

        else:
            stmt["status"] = "accepted"

    # Save profile
    if prof_data is not None and accepted_rules_added > 0:
        write_text_lf(prof_path, yaml.safe_dump(prof_data, sort_keys=False, allow_unicode=True))

    # Save ledger
    write_ledger(ledger_path, statements)

    cov_pct, cov_count, rel_count = calculate_coverage(statements)
    print("Applied updates:")
    print(f"  Accepted rules added to profile: {accepted_rules_added}")
    print(f"  Accepted notes added to .agents/notes/: {accepted_notes_added}")
    print(f"  Routed to blueprint contracts: {routed_count}")
    print(f"  Dropped statements: {dropped_count}")
    print(f"Coverage is now {cov_pct}% ({cov_count}/{rel_count} rule-candidate and derivable statements covered or accepted).")


def cmd_status(root: Path):
    ledger_path = root / ".agents" / "legacy-parity.md"
    if not ledger_path.is_file():
        sys.exit("Error: .agents/legacy-parity.md does not exist. Run inventory first.")

    statements = read_ledger(ledger_path)

    # Re-check pending derivable statements against blueprints if present
    blueprints = load_blueprints(root)
    updated = False
    if blueprints:
        for s in statements:
            if s.get("status") == "pending" and s.get("class", "").startswith("derivable-"):
                s_class = s["class"]
                text = s["text"]
                if s_class == "derivable-tokens" and "tokens" in blueprints:
                    token_matches = re.findall(r"(--[a-zA-Z0-9_-]+)", text)
                    for tm in token_matches:
                        if tm in blueprints["tokens"]:
                            s["status"] = "covered"
                            s["reason"] = f"matched blueprint token {tm}"
                            updated = True
                            break
                elif s_class == "derivable-data" and "data" in blueprints:
                    table_matches = re.findall(r"(?:model|TABLE|interface|type)\s+([A-Za-z0-9_]+)", text, re.IGNORECASE)
                    for tm in table_matches:
                        if tm.lower() in blueprints["data"].lower():
                            s["status"] = "covered"
                            s["reason"] = f"matched blueprint data model {tm}"
                            updated = True
                            break
                elif s_class == "derivable-layout" and "layout" in blueprints:
                    bp_matches = re.findall(r"(\d+px)", text)
                    for bm in bp_matches:
                        if bm in blueprints["layout"]:
                            s["status"] = "covered"
                            s["reason"] = f"matched blueprint layout {bm}"
                            updated = True
                            break
                elif s_class == "derivable-ui" and "ui" in blueprints:
                    comp_matches = re.findall(r"<([A-Z][a-zA-Z0-9]+)", text)
                    for cm in comp_matches:
                        if cm in blueprints["ui"]:
                            s["status"] = "covered"
                            s["reason"] = f"matched blueprint ui component {cm}"
                            updated = True
                            break
        if updated:
            write_ledger(ledger_path, statements)

    counts = {"pending": 0, "covered": 0, "accepted": 0, "dropped": 0, "routed": 0}
    pending_by_folder_and_class = {}
    pending_local_rule_count = 0
    pending_local_derivable_count = 0

    for s in statements:
        st = s.get("status", "pending")
        counts[st] = counts.get(st, 0) + 1
        if st == "pending":
            s_file = s.get("file", "")
            p = Path(s_file)
            if len(p.parts) > 1:
                if len(p.parts) >= 3 and p.parts[0] == ".agents" and p.parts[1] == "skills":
                    folder = "/".join(p.parts[:3])
                else:
                    folder = str(p.parent).replace("\\", "/")
            else:
                folder = "."
            s_class = s.get("class", "unknown")
            src_class = s.get("source_class", "local")

            key = (folder, src_class)
            pending_by_folder_and_class.setdefault(key, {})
            pending_by_folder_and_class[key][s_class] = pending_by_folder_and_class[key].get(s_class, 0) + 1

            if src_class == "local":
                if s_class == "rule-candidate":
                    pending_local_rule_count += 1
                elif s_class in ("derivable-data", "derivable-tokens", "derivable-ui", "derivable-layout"):
                    pending_local_derivable_count += 1

    decision_sources = read_ledger_decision_sources(ledger_path)
    cov_pct, cov_count, rel_count = calculate_coverage(statements)

    print("Legacy Parity Status:")
    print(f"  Pending:  {counts['pending']}")
    print(f"  Covered:  {counts['covered']}")
    print(f"  Routed:   {counts['routed']}")
    print(f"  Accepted: {counts['accepted']}")
    print(f"  Dropped:  {counts['dropped']}")
    print(f"\nCoverage: {cov_pct}% ({cov_count}/{rel_count} rule-candidate and derivable statements covered or accepted).")

    if pending_by_folder_and_class:
        print("\nPending statements by source folder and class:")
        for (folder, src_class), class_counts in sorted(pending_by_folder_and_class.items()):
            print(f"  {folder} ({src_class}):")
            for c_name, cnt in sorted(class_counts.items()):
                print(f"    {c_name}: {cnt}")

    if decision_sources:
        print(f"\nSources needing decision ({len(decision_sources)}):")
        for ds in decision_sources:
            print(f"  - {ds['path']} ({ds['class']}): {ds['signals']}")

    exit_causes = []
    if pending_local_rule_count > 0:
        exit_causes.append(f"{pending_local_rule_count} pending local rule-candidate statement(s)")
    if pending_local_derivable_count > 0:
        exit_causes.append(f"{pending_local_derivable_count} pending local derivable statement(s)")
    if decision_sources:
        paths = ", ".join(ds["path"] for ds in decision_sources)
        exit_causes.append(f"source(s) need decision: {paths}")

    if exit_causes:
        print(f"\nExit 1: {'; '.join(exit_causes)}.")
        sys.exit(1)

    print("\nAll rule-candidate and derivable statements resolved.")
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser(description="Legacy parity importer for Build Forge.")
    sub = ap.add_subparsers(dest="command", required=True)

    p_inv = sub.add_parser("inventory", help="Inventory legacy statements into ledger.")
    p_inv.add_argument("--include-skipped", action="store_true", help="Include skipped sources in inventory statements.")
    p_inv.add_argument("--root", default=".", help="Project root directory.")

    p_batch = sub.add_parser("batch", help="Print pending statements for an area.")
    p_batch.add_argument("--area", required=True, help="Area to inspect (naming, tokens, data, etc.).")
    p_batch.add_argument("--limit", type=int, default=15, help="Maximum statements to show (default 15).")
    p_batch.add_argument("--root", default=".", help="Project root directory.")

    p_apply = sub.add_parser("apply", help="Apply accept/drop/route decisions to profile, blueprints, and ledger.")
    p_apply.add_argument("--accept", default="", help="Comma-separated IDs to accept.")
    p_apply.add_argument("--drop", default="", help="Comma-separated IDs to drop.")
    p_apply.add_argument("--route", default="", help="Comma-separated IDs to route into blueprint contracts.")
    p_apply.add_argument("--route-class", default="", help="Statement class to route (e.g. derivable).")
    p_apply.add_argument("--yes", action="store_true", help="Confirm batch routing of a class.")
    p_apply.add_argument("--reason", default="", help="Reason for drop.")
    p_apply.add_argument("--root", default=".", help="Project root directory.")

    p_status = sub.add_parser("status", help="Check parity status and exit 1 if blocking items are pending.")
    p_status.add_argument("--root", default=".", help="Project root directory.")

    args = ap.parse_args()
    root = Path(args.root).resolve()

    if args.command == "inventory":
        cmd_inventory(root, include_skipped=args.include_skipped)
    elif args.command == "batch":
        cmd_batch(root, args.area, args.limit)
    elif args.command == "apply":
        accept_ids = [x.strip() for x in args.accept.split(",") if x.strip()]
        drop_ids = [x.strip() for x in args.drop.split(",") if x.strip()]
        route_ids = [x.strip() for x in args.route.split(",") if x.strip()]
        cmd_apply(root, accept_ids, drop_ids, route_ids, args.route_class, args.yes, args.reason)
    elif args.command == "status":
        cmd_status(root)


if __name__ == "__main__":
    main()
