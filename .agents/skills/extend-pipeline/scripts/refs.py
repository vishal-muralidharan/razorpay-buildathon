#!/usr/bin/env python3
"""Manage third party references and external skills for Build Forge.

Dependency-free standard library script with PyYAML.
Subcommands:
  fetch       Fetch repository or directory for inspection
  vet         Security scan on a skill directory
  add         Install and pin an approved reference
  list        List configured references
  verify      Verify installed reference files against lock file
  update      Preview or apply updates for an installed reference
  remove      Delete an installed reference and its configuration
  restore     Restore vendor files at pinned commits from lock
  due         List references due for a specific pipeline stage
  migrate     Migrate external_references from project profile
"""
import os
import re
import sys
import shutil
import tempfile
import argparse
import json
import hashlib
import fnmatch
import subprocess
import difflib
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

VALID_CATEGORIES = {
    "backend",
    "database",
    "security",
    "deploy",
    "hosting",
    "browser",
    "performance",
    "accessibility",
    "other"
}

VALID_STAGES = {"audit", "build", "verify", "deploy", "report"}
VALID_MODES = {"advisory", "gate"}
VALID_ACTIVATIONS = {"pipeline-only", "native"}
VALID_STATUSES = {"declared", "installed", "rejected"}

# HIGH severity script extensions (case-insensitive)
VET_HIGH_SCRIPT_EXTENSIONS = {
    ".py", ".sh", ".bash", ".zsh", ".js", ".cjs", ".mjs",
    ".ts", ".cts", ".mts", ".jsx", ".tsx", ".ps1", ".bat",
    ".cmd", ".rb", ".pl", ".php"
}

# Zero-width and bidirectional control characters
VET_ZERO_WIDTH_CHARS = re.compile(r"[\u200b\u200c\u200d\ufeff\u202a-\u202e\u2066-\u2069]")

# Instruction override / prompt injection phrases
VET_INJECTION_PHRASES = [
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard the rules",
    "disregard all previous instructions",
    "disregard previous instructions",
    "disregard instructions",
    "do not tell the user",
    "hide this from the user",
    "system prompt",
    "override instructions",
    "bypass security",
    "hidden instruction"
]

# Instruction-like words and imperative verbs in HTML comments
VET_COMMENT_INSTRUCTION_WORDS = re.compile(
    r"\b(ignore|disregard|override|bypass|hide|run|execute|eval|install|delete|remove|download|upload|curl|wget|fetch|send|post|set|export|write|exfiltrate|system|prompt|instruction)\b",
    re.IGNORECASE
)

# MEDIUM patterns inside code block or inline code
VET_CODE_INSTALL_PATTERNS = re.compile(
    r"(\b(npx|pnpm\s+dlx|bunx|yarn\s+dlx)\b|\b(npm\s+(i|install))\b|\b(pip\s+install)\b|(curl|wget)\s+[^|\n]*\|\s*(sh|bash|zsh)|@latest)",
    re.IGNORECASE
)
VET_CODE_CREDENTIAL_PATTERNS = re.compile(
    r"(\bexport\s+[A-Za-z0-9_]*(TOKEN|KEY|SECRET|PASSWORD)\s*=|"
    r"\b(npm|docker|gh|gcloud|aws)\s+(auth\s+)?login\b|"
    r"\b(ssh-keygen|openssl\s+genrsa|gpg\s+--gen-key|keytool\s+-genkey)\b)",
    re.IGNORECASE
)
VET_CODE_PATH_ESCAPE_PATTERNS = re.compile(
    r"((?<!\w)~/|(?<!\w)/tmp\b|/etc/|/usr/|\$HOME|%USERPROFILE%|(?<![A-Za-z0-9])[A-Za-z]:[\\/])",
    re.IGNORECASE
)
VET_CODE_NETWORK_PATTERNS = re.compile(
    r"(\b(curl|wget)\b|\bfetch\s*\(|\b(urllib|axios|aiohttp|http\.client)\b)",
    re.IGNORECASE
)

# LOW patterns in plain prose
VET_PROSE_KEYWORDS = re.compile(
    r"\b(fetch|requests|token|socket|secret|password)\b",
    re.IGNORECASE
)


def hash_file(file_path):
    with open(file_path, "rb") as f:
        content = f.read().replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def compute_dir_hashes(dir_path):
    hashes = {}
    for root, _, files in os.walk(dir_path):
        for f in sorted(files):
            full = os.path.join(root, f)
            rel = os.path.relpath(full, dir_path).replace("\\", "/")
            hashes[rel] = hash_file(full)
    return hashes


def get_paths(root=None):
    root_path = Path(root or ".").resolve()
    agents_dir = root_path / ".agents"
    yaml_path = agents_dir / "references.yaml"
    lock_path = agents_dir / "references.lock.json"
    return root_path, yaml_path, lock_path


def load_references(yaml_path):
    if not yaml_path.is_file():
        return {"schema_version": 1, "vendor_in_git": False, "references": []}
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("schema_version", 1)
    data.setdefault("vendor_in_git", False)
    data.setdefault("references", [])
    return data


def save_references(yaml_path, data):
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)


def load_lock(lock_path):
    if not lock_path.is_file():
        return {}
    with open(lock_path, "r", encoding="utf-8") as f:
        return json.load(f) or {}


def save_lock(lock_path, lock_data):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as f:
        json.dump(lock_data, f, indent=2, sort_keys=True)
        f.write("\n")


# -------------------------------------------------------------------------
# Collision Detection & Deduplication Helpers
# -------------------------------------------------------------------------
def get_skill_frontmatter_name(skill_md_path: Path) -> str:
    """Read skill name from YAML frontmatter if present."""
    if not skill_md_path.is_file():
        return ""
    try:
        content = skill_md_path.read_text(encoding="utf-8", errors="ignore")
        m = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if m:
            data = yaml.safe_load(m.group(1)) or {}
            if isinstance(data, dict):
                return str(data.get("name", "")).strip()
    except Exception:
        pass
    return ""


def classify_folders(dir_vendor: Path, dir_skills: Path) -> tuple:
    """Compare normalized file hash trees between vendor and skills directories."""
    if not dir_vendor.is_dir() or not dir_skills.is_dir():
        return "modified", [("directory", "missing")]
    hashes_v = compute_dir_hashes(dir_vendor)
    hashes_s = compute_dir_hashes(dir_skills)
    if hashes_v == hashes_s:
        return "identical", []
    diffs = []
    all_files = sorted(set(hashes_v.keys()) | set(hashes_s.keys()))
    for f in all_files:
        if f not in hashes_v:
            diffs.append((f, "added in skills (missing in vendor)"))
        elif f not in hashes_s:
            diffs.append((f, "removed in skills (missing in skills)"))
        elif hashes_v[f] != hashes_s[f]:
            diffs.append((f, "content differs"))
    return "modified", diffs


def find_reference_collisions(root_path: Path, ref_data: dict = None) -> list:
    """Detect collisions between .agents/vendor and .agents/skills.

    For a pipeline-only reference: collision if .agents/skills/<name> exists or frontmatter name matches.
    For a native reference: collision if .agents/vendor/<name> exists.
    Also handles non-reference vendor folders that match skills.
    """
    if ref_data is None:
        _, yaml_path, _ = get_paths(root_path)
        ref_data = load_references(yaml_path)

    skills_dir = root_path / ".agents" / "skills"
    vendor_dir = root_path / ".agents" / "vendor"

    collisions = []
    seen_pairs = set()

    skill_folders = {}
    if skills_dir.is_dir():
        for d in sorted(skills_dir.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                fm_name = get_skill_frontmatter_name(d / "SKILL.md")
                skill_folders[d.name] = fm_name

    refs = ref_data.get("references", [])
    known_ref_names = set()

    for r in refs:
        rname = r.get("name")
        if not rname:
            continue
        known_ref_names.add(rname)
        act = r.get("activation", "pipeline-only")

        if act == "native":
            v_path = vendor_dir / rname
            s_path = skills_dir / rname
            if v_path.is_dir() and s_path.is_dir():
                pair_key = (rname, rname)
                if pair_key not in seen_pairs:
                    seen_pairs.add(pair_key)
                    cls, diffs = classify_folders(v_path, s_path)
                    collisions.append({
                        "name": rname,
                        "skill_dir_name": rname,
                        "vendor_path": v_path,
                        "skills_path": s_path,
                        "classification": cls,
                        "diff_files": diffs
                    })
        else:
            v_path = vendor_dir / rname
            # Check direct name match
            if (skills_dir / rname).is_dir():
                pair_key = (rname, rname)
                if pair_key not in seen_pairs:
                    seen_pairs.add(pair_key)
                    s_path = skills_dir / rname
                    cls, diffs = classify_folders(v_path, s_path) if v_path.is_dir() else ("modified", [("vendor", "missing")])
                    collisions.append({
                        "name": rname,
                        "skill_dir_name": rname,
                        "vendor_path": v_path,
                        "skills_path": s_path,
                        "classification": cls,
                        "diff_files": diffs
                    })
            # Check frontmatter name match
            for sdir_name, fm_name in skill_folders.items():
                if fm_name == rname and sdir_name != rname:
                    pair_key = (rname, sdir_name)
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        s_path = skills_dir / sdir_name
                        cls, diffs = classify_folders(v_path, s_path) if v_path.is_dir() else ("modified", [("vendor", "missing")])
                        collisions.append({
                            "name": rname,
                            "skill_dir_name": sdir_name,
                            "vendor_path": v_path,
                            "skills_path": s_path,
                            "classification": cls,
                            "diff_files": diffs
                        })

    # Non-reference vendor folders
    if vendor_dir.is_dir():
        for vd in sorted(vendor_dir.iterdir()):
            if vd.is_dir() and not vd.name.startswith(".") and vd.name not in known_ref_names:
                vname = vd.name
                if (skills_dir / vname).is_dir():
                    pair_key = (vname, vname)
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        s_path = skills_dir / vname
                        cls, diffs = classify_folders(vd, s_path)
                        collisions.append({
                            "name": vname,
                            "skill_dir_name": vname,
                            "vendor_path": vd,
                            "skills_path": s_path,
                            "classification": cls,
                            "diff_files": diffs
                        })

    return collisions


def remove_agent_links_for_skill(root_path: Path, skill_dir_name: str) -> list:
    """Find and remove symlinks pointing to .agents/skills/<skill_dir_name>."""
    target_skill_path = (root_path / ".agents" / "skills" / skill_dir_name).resolve()
    removed_links = []
    for candidate in [
        root_path / ".claude" / "skills",
        root_path / ".cursor" / "skills",
        root_path / ".windsurf" / "skills",
    ]:
        if candidate.is_dir():
            for item in candidate.iterdir():
                if item.is_symlink():
                    try:
                        dest = item.resolve()
                        if dest == target_skill_path:
                            item.unlink()
                            removed_links.append(item.relative_to(root_path).as_posix())
                    except Exception:
                        pass
    return removed_links


# -------------------------------------------------------------------------
# Subcommand: fetch
# -------------------------------------------------------------------------
def git_clone_or_fetch(url, ref, target_dir):
    """Clone or fetch a repository at a given ref (branch, tag, or commit SHA)."""
    os.makedirs(target_dir, exist_ok=True)
    clone_cmd = ["git", "clone", "--depth", "1"]
    if ref and ref != "HEAD":
        clone_cmd += ["--branch", ref]
    clone_cmd += [url, str(target_dir)]
    res = subprocess.run(clone_cmd, capture_output=True, text=True)
    if res.returncode == 0:
        return res
    # If clone failed (e.g. ref is a commit SHA), use git init + fetch + checkout
    shutil.rmtree(target_dir, ignore_errors=True)
    os.makedirs(target_dir, exist_ok=True)
    subprocess.run(["git", "init"], cwd=target_dir, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", url], cwd=target_dir, capture_output=True)
    fetch_target = ref if (ref and ref != "HEAD") else "HEAD"
    res_fetch = subprocess.run(["git", "fetch", "--depth", "1", "origin", fetch_target], cwd=target_dir, capture_output=True, text=True)
    if res_fetch.returncode == 0:
        res_co = subprocess.run(["git", "checkout", "FETCH_HEAD"], cwd=target_dir, capture_output=True, text=True)
        if res_co.returncode == 0:
            return subprocess.CompletedProcess(args=clone_cmd, returncode=0, stdout=res_fetch.stdout, stderr="")
    return res


def cmd_fetch(args):
    url = args.url
    subpath = args.subpath or ""
    ref = args.ref or "HEAD"
    out_dir = args.out

    temp_created = False
    if not out_dir:
        target_dir = tempfile.mkdtemp(prefix="bf-fetch-")
        temp_created = True
    else:
        target_dir = os.path.abspath(out_dir)
        os.makedirs(target_dir, exist_ok=True)

    try:
        # Check if local directory or git url
        is_local = os.path.isdir(url)
        commit_sha = "local"
        if is_local:
            src = os.path.abspath(url)
            for item in os.listdir(src):
                s_item = os.path.join(src, item)
                d_item = os.path.join(target_dir, item)
                if os.path.isdir(s_item):
                    shutil.copytree(s_item, d_item, dirs_exist_ok=True)
                else:
                    shutil.copy2(s_item, d_item)
            try:
                res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=src, capture_output=True, text=True)
                if res.returncode == 0:
                    commit_sha = res.stdout.strip()
            except Exception:
                pass
        else:
            # Git clone
            res = git_clone_or_fetch(url, ref, target_dir)
            if res.returncode != 0:
                sys.exit(f"Fetch failed: git clone error:\n{res.stderr}")
            res_rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=target_dir, capture_output=True, text=True)
            if res_rev.returncode == 0:
                commit_sha = res_rev.stdout.strip()

        # Locate inspect target
        inspect_root = os.path.join(target_dir, subpath) if subpath else target_dir
        if not os.path.exists(inspect_root):
            sys.exit(f"Subpath '{subpath}' does not exist in the fetched repository.")

        # Find license
        license_info = "Not found"
        for name in ["LICENSE", "LICENSE.md", "LICENSE.txt"]:
            lpath = os.path.join(inspect_root, name)
            if os.path.isfile(lpath):
                with open(lpath, "r", encoding="utf-8", errors="ignore") as f:
                    first_line = f.readline().strip()
                license_info = f"{name} ({first_line[:60]})"
                break

        # Find skills
        skills_found = []
        for root, dirs, files in os.walk(inspect_root):
            if "SKILL.md" in files:
                skill_dir = root
                skill_md_path = os.path.join(skill_dir, "SKILL.md")
                name = os.path.basename(skill_dir)
                desc = "No description"
                try:
                    with open(skill_md_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    if content.startswith("---"):
                        parts = content.split("---", 2)
                        if len(parts) >= 3:
                            fm = yaml.safe_load(parts[1]) or {}
                            name = fm.get("name", name)
                            desc = fm.get("description", desc)
                except Exception:
                    pass

                skill_files = []
                for sroot, _, sfiles in os.walk(skill_dir):
                    for sf in sfiles:
                        skill_files.append(os.path.relpath(os.path.join(sroot, sf), skill_dir).replace("\\", "/"))
                skills_found.append({
                    "name": name,
                    "description": desc,
                    "path": os.path.relpath(skill_dir, inspect_root).replace("\\", "/"),
                    "files": sorted(skill_files)
                })

        print(f"Fetched repository: {url}")
        print(f"Commit SHA: {commit_sha}")
        print(f"License: {license_info}")
        print(f"Skills discovered: {len(skills_found)}")
        for s in skills_found:
            print(f"\n  Skill: {s['name']}")
            print(f"  Description: {s['description']}")
            print(f"  Path in repo: {s['path']}")
            print(f"  Files ({len(s['files'])}): {', '.join(s['files'][:10])}" + ("..." if len(s['files']) > 10 else ""))

    finally:
        if temp_created and not out_dir:
            shutil.rmtree(target_dir, ignore_errors=True)


# -------------------------------------------------------------------------
# Subcommand: vet
# -------------------------------------------------------------------------
def split_line_code_spans(line):
    """Split line into list of (is_code, text) segments based on markdown backticks."""
    segments = []
    pattern = re.compile(r"(`+)(.+?)\1")
    last_end = 0
    for match in pattern.finditer(line):
        start, end = match.span()
        if start > last_end:
            segments.append((False, line[last_end:start]))
        segments.append((True, match.group(2)))
        last_end = end
    if last_end < len(line):
        segments.append((False, line[last_end:]))
    return segments


def run_vet_scan(scan_dir):
    """Run comprehensive security vetting scan across files in scan_dir.

    Returns a list of tuples: (severity, rel_path, line_number_or_None, message).
    """
    findings = []
    scan_dir = os.path.abspath(scan_dir)

    for root, dirs, files in os.walk(scan_dir):
        if ".git" in dirs:
            dirs.remove(".git")

        for f in sorted(files):
            file_path = os.path.join(root, f)
            rel_path = os.path.relpath(file_path, scan_dir).replace("\\", "/")
            _, ext = os.path.splitext(f)
            ext_lower = ext.lower()

            # 1. HIGH: Script files by extension
            if ext_lower in VET_HIGH_SCRIPT_EXTENSIONS:
                findings.append(("HIGH", rel_path, None, f"Executable script file present: {rel_path}"))

            # 2. HIGH: Executable bit
            try:
                st = os.stat(file_path)
                if st.st_mode & 0o111:
                    findings.append(("HIGH", rel_path, None, f"Executable permission bit set on file: mode {oct(st.st_mode)}"))
            except Exception:
                pass

            # Read file contents
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
                    lines = fh.readlines()
            except Exception as e:
                findings.append(("MEDIUM", rel_path, None, f"Could not read file: {e}"))
                continue

            # Check if file has frontmatter (starts with --- on line 1)
            frontmatter_end = 0
            if lines and lines[0].strip() == "---":
                for idx in range(1, len(lines)):
                    if lines[idx].strip() == "---":
                        frontmatter_end = idx + 1
                        break

            in_fenced_code = False
            fence_marker = None
            in_html_comment = False
            comment_start_line = 0
            comment_buffer = []

            for line_idx, line in enumerate(lines, 1):
                # 3. HIGH: Shebang line on line 1
                if line_idx == 1 and line.startswith("#!"):
                    findings.append(("HIGH", rel_path, 1, f"Shebang line detected on line 1: '{line.strip()}'"))

                # 4. HIGH: Zero-width or bidirectional unicode characters
                if VET_ZERO_WIDTH_CHARS.search(line):
                    findings.append(("HIGH", rel_path, line_idx, "Zero-width or bidirectional Unicode character discovered."))

                # 5. HIGH: Instruction override phrases
                line_lower = line.lower()
                for phrase in VET_INJECTION_PHRASES:
                    if phrase in line_lower:
                        findings.append(("HIGH", rel_path, line_idx, f"Instruction override phrase detected: '{phrase}'"))
                        break

                # Lines inside frontmatter are not scanned for HTML comments, code blocks, or prose keywords
                if line_idx <= frontmatter_end:
                    continue

                # Handle multi-line HTML comment state
                if in_html_comment:
                    close_pos = line.find("-->")
                    if close_pos == -1:
                        comment_buffer.append(line)
                        continue
                    else:
                        comment_buffer.append(line[:close_pos])
                        full_body = "".join(comment_buffer).strip()
                        snippet = (full_body.replace("\n", " ")[:60]).strip()
                        if re.match(r"^e\.g\b", full_body, re.IGNORECASE):
                            findings.append(("LOW", rel_path, comment_start_line, f"Placeholder HTML comment: '<!-- {snippet} -->'"))
                        elif VET_COMMENT_INSTRUCTION_WORDS.search(full_body):
                            m_w = VET_COMMENT_INSTRUCTION_WORDS.search(full_body).group(0)
                            findings.append(("HIGH", rel_path, comment_start_line, f"HTML comment containing instruction or imperative verb detected ('{m_w}'): '<!-- {snippet} -->'"))
                        else:
                            findings.append(("MEDIUM", rel_path, comment_start_line, f"HTML comment present in text: '<!-- {snippet} -->'"))
                        in_html_comment = False
                        comment_buffer = []
                        line = line[close_pos + 3:]
                        if not line.strip():
                            continue

                # Check for fenced code block toggle
                stripped = line.strip()
                if not in_fenced_code:
                    if stripped.startswith("```") or stripped.startswith("~~~"):
                        in_fenced_code = True
                        fence_marker = stripped[:3]
                        continue
                else:
                    if stripped.startswith(fence_marker):
                        in_fenced_code = False
                        fence_marker = None
                        continue

                # If inside fenced code block, check MEDIUM patterns on the whole line
                if in_fenced_code:
                    m = VET_CODE_INSTALL_PATTERNS.search(line)
                    if m:
                        findings.append(("MEDIUM", rel_path, line_idx, f"Download or install command in code: '{m.group(0)}'"))
                    m = VET_CODE_CREDENTIAL_PATTERNS.search(line)
                    if m:
                        findings.append(("MEDIUM", rel_path, line_idx, f"Credential command in code: '{m.group(0)}'"))
                    m = VET_CODE_PATH_ESCAPE_PATTERNS.search(line)
                    if m:
                        findings.append(("MEDIUM", rel_path, line_idx, f"Path referencing outside project boundary in code: '{m.group(0)}'"))
                    m = VET_CODE_NETWORK_PATTERNS.search(line)
                    if m:
                        findings.append(("MEDIUM", rel_path, line_idx, f"Network call in code: '{m.group(0)}'"))
                    continue

                # Outside fenced code blocks: extract inline code spans and non-code spans
                segments = split_line_code_spans(line)
                new_segments = []
                for is_code, seg_text in segments:
                    if is_code:
                        new_segments.append((True, seg_text))
                    else:
                        # Extract HTML comments from non-code text
                        pos = 0
                        while pos < len(seg_text):
                            open_pos = seg_text.find("<!--", pos)
                            if open_pos == -1:
                                new_segments.append((False, seg_text[pos:]))
                                break
                            if open_pos > pos:
                                new_segments.append((False, seg_text[pos:open_pos]))
                            close_pos = seg_text.find("-->", open_pos + 4)
                            if close_pos != -1:
                                comment_body = seg_text[open_pos + 4 : close_pos].strip()
                                snippet = (comment_body.replace("\n", " ")[:60]).strip()
                                if re.match(r"^e\.g\b", comment_body, re.IGNORECASE):
                                    findings.append(("LOW", rel_path, line_idx, f"Placeholder HTML comment: '<!-- {snippet} -->'"))
                                elif VET_COMMENT_INSTRUCTION_WORDS.search(comment_body):
                                    m_w = VET_COMMENT_INSTRUCTION_WORDS.search(comment_body).group(0)
                                    findings.append(("HIGH", rel_path, line_idx, f"HTML comment containing instruction or imperative verb detected ('{m_w}'): '<!-- {snippet} -->'"))
                                else:
                                    findings.append(("MEDIUM", rel_path, line_idx, f"HTML comment present in text: '<!-- {snippet} -->'"))
                                pos = close_pos + 3
                            else:
                                in_html_comment = True
                                comment_start_line = line_idx
                                comment_buffer = [seg_text[open_pos + 4 :]]
                                pos = len(seg_text)
                                break

                # Scan processed segments
                for is_code, seg_text in new_segments:
                    if is_code:
                        m = VET_CODE_INSTALL_PATTERNS.search(seg_text)
                        if m:
                            findings.append(("MEDIUM", rel_path, line_idx, f"Download or install command in code: '{m.group(0)}'"))
                        m = VET_CODE_CREDENTIAL_PATTERNS.search(seg_text)
                        if m:
                            findings.append(("MEDIUM", rel_path, line_idx, f"Credential command in code: '{m.group(0)}'"))
                        m = VET_CODE_PATH_ESCAPE_PATTERNS.search(seg_text)
                        if m:
                            findings.append(("MEDIUM", rel_path, line_idx, f"Path referencing outside project boundary in code: '{m.group(0)}'"))
                        m = VET_CODE_NETWORK_PATTERNS.search(seg_text)
                        if m:
                            findings.append(("MEDIUM", rel_path, line_idx, f"Network call in code: '{m.group(0)}'"))
                    else:
                        for m in VET_PROSE_KEYWORDS.finditer(seg_text):
                            findings.append(("LOW", rel_path, line_idx, f"Informational keyword in prose: '{m.group(0)}'"))

            # Handle unclosed HTML comment at end of file
            if in_html_comment and comment_buffer:
                full_body = "".join(comment_buffer).strip()
                snippet = (full_body.replace("\n", " ")[:60]).strip()
                if re.match(r"^e\.g\b", full_body, re.IGNORECASE):
                    findings.append(("LOW", rel_path, comment_start_line, f"Placeholder HTML comment: '<!-- {snippet} -->'"))
                elif VET_COMMENT_INSTRUCTION_WORDS.search(full_body):
                    m_w = VET_COMMENT_INSTRUCTION_WORDS.search(full_body).group(0)
                    findings.append(("HIGH", rel_path, comment_start_line, f"HTML comment containing instruction or imperative verb detected ('{m_w}'): '<!-- {snippet} -->'"))
                else:
                    findings.append(("MEDIUM", rel_path, comment_start_line, f"HTML comment present in text: '<!-- {snippet} -->'"))

    return findings


def print_vet_report(scan_dir, findings, show_all=False, as_json=False):
    """Print formatted vetting report matching severity model."""
    if as_json:
        totals = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        by_file = {}
        findings_list = []
        for sev, file_p, line_n, msg in findings:
            totals[sev] = totals.get(sev, 0) + 1
            if file_p not in by_file:
                by_file[file_p] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
            by_file[file_p][sev] = by_file[file_p].get(sev, 0) + 1
            findings_list.append({
                "severity": sev,
                "file": file_p,
                "line": line_n,
                "message": msg
            })
        data = {
            "scan_dir": scan_dir,
            "totals": totals,
            "files": by_file,
            "findings": findings_list
        }
        print(json.dumps(data, indent=2))
        return

    print(f"=== VETTING REPORT FOR {scan_dir} ===")

    totals = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    by_file = {}
    for sev, file_p, line_n, msg in findings:
        totals[sev] = totals.get(sev, 0) + 1
        if file_p not in by_file:
            by_file[file_p] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        by_file[file_p][sev] = by_file[file_p].get(sev, 0) + 1

    if not findings:
        print("OK: No security findings detected.")
        print("\nSummary: 0 HIGH, 0 MEDIUM, 0 LOW finding(s).")
        print("Note: A clean scan is not proof of safety. Never execute unverified code.")
        return

    # 1. Summary first (counts per severity, per file)
    print("\nSummary by file:")
    for f_path in sorted(by_file.keys()):
        counts = by_file[f_path]
        print(f"  {f_path}: {counts.get('HIGH', 0)} HIGH, {counts.get('MEDIUM', 0)} MEDIUM, {counts.get('LOW', 0)} LOW")
    print(f"\nTotal: {totals.get('HIGH', 0)} HIGH, {totals.get('MEDIUM', 0)} MEDIUM, {totals.get('LOW', 0)} LOW finding(s).\n")

    # 2. Findings: HIGH and MEDIUM in full
    high_findings = [f for f in findings if f[0] == "HIGH"]
    med_findings = [f for f in findings if f[0] == "MEDIUM"]
    low_findings = [f for f in findings if f[0] == "LOW"]

    if show_all:
        for sev, file_p, line_n, msg in findings:
            loc = f"{file_p}:{line_n}" if line_n is not None else file_p
            print(f"[{sev}] {loc} - {msg}")
    else:
        for sev, file_p, line_n, msg in high_findings:
            loc = f"{file_p}:{line_n}" if line_n is not None else file_p
            print(f"[{sev}] {loc} - {msg}")

        for sev, file_p, line_n, msg in med_findings:
            loc = f"{file_p}:{line_n}" if line_n is not None else file_p
            print(f"[{sev}] {loc} - {msg}")

        # LOW collapsed into 1 count per file
        low_by_file = {}
        for sev, file_p, line_n, msg in low_findings:
            low_by_file[file_p] = low_by_file.get(file_p, 0) + 1

        for file_p in sorted(low_by_file.keys()):
            cnt = low_by_file[file_p]
            plural = "finding" if cnt == 1 else "findings"
            print(f"[LOW] {file_p} - {cnt} informational {plural} (prose keywords or placeholder comments; use --all to view)")

    print("\nNote: A clean scan is not proof of safety. Never execute unverified code.")


def cmd_vet(args):
    scan_dir = os.path.abspath(args.dir)
    if not os.path.isdir(scan_dir):
        sys.exit(f"Vetting directory '{scan_dir}' not found.")

    findings = run_vet_scan(scan_dir)
    print_vet_report(scan_dir, findings, show_all=bool(args.all), as_json=bool(args.json))

    high_findings = [f for f in findings if f[0] == "HIGH"]
    if high_findings:
        sys.exit(1)
    sys.exit(0)


# -------------------------------------------------------------------------
# Subcommand: add
# -------------------------------------------------------------------------
def cmd_add(args):
    if not args.approved:
        sys.exit("Error: Adding a reference requires explicit user approval flag --approved.")

    name = args.name
    if not name or not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name):
        sys.exit(f"Error: Reference name '{name}' must be kebab-case (lowercase letters, numbers, hyphens).")

    root_path, yaml_path, lock_path = get_paths(args.root)
    ref_data = load_references(yaml_path)

    for r in ref_data.get("references", []):
        if r.get("name") == name:
            sys.exit(f"Error: Reference with name '{name}' already exists.")

    category = args.category
    if category not in VALID_CATEGORIES:
        sys.exit(f"Error: Category '{category}' must be one of: {sorted(VALID_CATEGORIES)}")

    used_by = [s.strip() for s in (args.used_by or "").split(",") if s.strip()]
    invalid_stages = set(used_by) - VALID_STAGES
    if invalid_stages or not used_by:
        sys.exit(f"Error: --used-by must contain valid stages: {sorted(VALID_STAGES)}")

    mode = args.mode or "advisory"
    if mode not in VALID_MODES:
        sys.exit(f"Error: Mode '{mode}' must be 'advisory' or 'gate'.")

    activation = args.activation or "pipeline-only"
    if activation not in VALID_ACTIVATIONS:
        sys.exit(f"Error: Activation '{activation}' must be 'pipeline-only' or 'native'.")

    source_input = args.source
    source_type = args.source_type or ("local" if os.path.exists(source_input) else "git")
    subpath = args.subpath or ""
    ref = args.ref or "HEAD"

    # Resolve target directory and check for collisions
    if activation == "native":
        target_dir = root_path / ".agents" / "skills" / name
        alt_dir = root_path / ".agents" / "vendor" / name
        if alt_dir.exists():
            sys.exit(
                f"Error: Collision detected. .agents/vendor/{name} already exists.\n"
                f"Options:\n"
                f"  1. Dedupe first: python3 .agents/skills/extend-pipeline/scripts/refs.py dedupe --name {name}\n"
                f"  2. Choose a different reference name with --name <new-name>"
            )
    else:
        target_dir = root_path / ".agents" / "vendor" / name
        alt_dir = root_path / ".agents" / "skills" / name
        if alt_dir.exists():
            sys.exit(
                f"Error: Collision detected. .agents/skills/{name} already exists.\n"
                f"Options:\n"
                f"  1. Dedupe first: python3 .agents/skills/extend-pipeline/scripts/refs.py dedupe --name {name}\n"
                f"  2. Choose a different reference name with --name <new-name>"
            )

    if target_dir.exists():
        sys.exit(f"Error: Target installation folder '{target_dir}' already exists.")

    pinned_commit = "unknown"
    license_text = "Unknown"

    with tempfile.TemporaryDirectory() as tmp_clone:
        if source_type == "local" or os.path.isdir(source_input):
            src_path = Path(source_input).resolve()
            pinned_commit = "local"
            try:
                res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=src_path, capture_output=True, text=True)
                if res.returncode == 0:
                    pinned_commit = res.stdout.strip()
            except Exception:
                pass
            skill_source = src_path / subpath if subpath else src_path
        else:
            res = git_clone_or_fetch(source_input, ref, tmp_clone)
            if res.returncode != 0:
                sys.exit(f"Clone failed during add: {res.stderr}")
            res_rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_clone, capture_output=True, text=True)
            if res_rev.returncode == 0:
                pinned_commit = res_rev.stdout.strip()
            skill_source = Path(tmp_clone) / subpath if subpath else Path(tmp_clone)

        if not skill_source.is_dir():
            sys.exit(f"Skill source path '{skill_source}' does not exist or is not a directory.")

        # Vetting summary at approval time
        vet_findings = run_vet_scan(str(skill_source))
        high_count = sum(1 for f in vet_findings if f[0] == "HIGH")
        med_count = sum(1 for f in vet_findings if f[0] == "MEDIUM")
        low_count = sum(1 for f in vet_findings if f[0] == "LOW")
        print(f"\nVetting summary for '{name}': {high_count} HIGH, {med_count} MEDIUM, {low_count} LOW finding(s).")
        print("Approval focuses on reviewing HIGH and MEDIUM findings. Review all warnings before deploying.\n")

        # Copy into destination
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill_source, target_dir)

    # Compute hashes and write to lock file
    rel_path_from_root = target_dir.relative_to(root_path).as_posix()
    dir_hashes = compute_dir_hashes(target_dir)

    lock_data = load_lock(lock_path)
    lock_data[name] = {
        "commit": pinned_commit,
        "path": rel_path_from_root,
        "files": dir_hashes
    }
    save_lock(lock_path, lock_data)

    triggers = {
        "paths": [p.strip() for p in (args.paths or "").split(",") if p.strip()],
        "keywords": [k.strip() for k in (args.keywords or "").split(",") if k.strip()]
    }

    new_entry = {
        "name": name,
        "kind": "skill",
        "category": category,
        "purpose": args.purpose or "",
        "source": {
            "type": source_type,
            "url": source_input,
            "subpath": subpath,
            "ref": ref
        },
        "pinned_commit": pinned_commit,
        "license": license_text,
        "activation": activation,
        "allow_scripts": bool(args.allow_scripts),
        "used_by": used_by,
        "triggers": triggers,
        "mode": mode,
        "status": "installed",
        "path": rel_path_from_root,
        "approved": True
    }

    ref_data["references"].append(new_entry)
    save_references(yaml_path, ref_data)

    print(f"Successfully added reference '{name}':")
    print(f"  Target path: {rel_path_from_root}")
    print(f"  Pinned commit: {pinned_commit}")
    print(f"  Mode: {mode}")
    print(f"  Stages: {', '.join(used_by)}")
    print(f"  Allow scripts: {bool(args.allow_scripts)}")


# -------------------------------------------------------------------------
# Subcommand: list
# -------------------------------------------------------------------------
def cmd_list(args):
    root_path, yaml_path, _ = get_paths(args.root)
    ref_data = load_references(yaml_path)
    refs = ref_data.get("references", [])

    if not refs:
        print("No references configured in .agents/references.yaml.")
        return

    collisions = {c["name"]: c for c in find_reference_collisions(root_path, ref_data)}

    print(f"{'NAME':<20} {'CATEGORY':<14} {'STATUS':<10} {'MODE':<10} {'SCRIPTS':<8} {'DUAL-HOME':<11} {'STAGES':<20} {'PATH'}")
    print("-" * 112)
    for r in refs:
        name = r.get("name", "")
        cat = r.get("category", "")
        status = r.get("status", "")
        mode = r.get("mode", "advisory")
        scripts = "yes" if r.get("allow_scripts") else "no"
        stages = ", ".join(r.get("used_by", []))
        path_str = r.get("path", "")
        dual_home = collisions[name]["classification"] if name in collisions else "-"
        print(f"{name:<20} {cat:<14} {status:<10} {mode:<10} {scripts:<8} {dual_home:<11} {stages:<20} {path_str}")


# -------------------------------------------------------------------------
# Subcommand: verify
# -------------------------------------------------------------------------
def cmd_verify(args):
    root_path, yaml_path, lock_path = get_paths(args.root)
    ref_data = load_references(yaml_path)

    # 1. Collision warnings
    collisions = find_reference_collisions(root_path, ref_data)
    for c in collisions:
        print(
            f"WARN: Dual-homed skill collision for '{c['name']}': exists in both "
            f".agents/vendor/{c['name']} and .agents/skills/{c['skill_dir_name']} ({c['classification']}). "
            f"Run: python3 .agents/skills/extend-pipeline/scripts/refs.py dedupe"
        )

    # 2. Orphan vendor folders
    vendor_dir = root_path / ".agents" / "vendor"
    if vendor_dir.is_dir():
        known_vendor_names = {r.get("name") for r in ref_data.get("references", [])}
        for item in sorted(vendor_dir.iterdir()):
            if item.is_dir() and item.name not in known_vendor_names and not item.name.startswith("."):
                print(f"WARN: Orphan vendor folder found: .agents/vendor/{item.name} has no entry in .agents/references.yaml")

    refs = [r for r in ref_data.get("references", []) if r.get("status") == "installed"]

    if not refs:
        print("No installed references found. Skipping reference verification.")
        sys.exit(0)

    if not lock_path.is_file():
        sys.exit("Error: .agents/references.lock.json not found for installed references.")

    lock_data = load_lock(lock_path)
    failed = False

    for r in refs:
        name = r.get("name")
        ref_lock = lock_data.get(name)
        if not ref_lock:
            print(f"ERROR: Lock entry missing for reference '{name}'.")
            failed = True
            continue

        target_dir = root_path / r.get("path", "")
        if not target_dir.is_dir():
            if not ref_data.get("vendor_in_git", False) and str(r.get("path", "")).startswith(".agents/vendor/"):
                print(f"WARN: Installed directory not found for '{name}': {target_dir} (run: python3 .agents/skills/extend-pipeline/scripts/refs.py restore)")
                continue
            print(f"ERROR: Installed directory not found for '{name}': {target_dir}")
            failed = True
            continue

        expected_files = ref_lock.get("files", {})
        current_hashes = compute_dir_hashes(target_dir)

        # Check missing or modified
        for rel_f, expected_hash in expected_files.items():
            if rel_f not in current_hashes:
                print(f"ERROR: [{name}] missing file: {rel_f}")
                failed = True
            elif current_hashes[rel_f] != expected_hash:
                print(f"ERROR: [{name}] modified file: {rel_f}")
                failed = True

        # Check extra files
        for rel_f in current_hashes:
            if rel_f not in expected_files:
                print(f"ERROR: [{name}] extra file: {rel_f}")
                failed = True

    if failed:
        sys.exit(1)

    print("Verify ok: All installed third party references match the lock file.")
    sys.exit(0)


# -------------------------------------------------------------------------
# Subcommand: dedupe
# -------------------------------------------------------------------------
def cmd_dedupe(args):
    root_path, yaml_path, _ = get_paths(args.root)
    ref_data = load_references(yaml_path)
    collisions = find_reference_collisions(root_path, ref_data)

    if args.name:
        collisions = [c for c in collisions if c["name"] == args.name]
        if not collisions:
            print(f"No collision found for reference '{args.name}'.")
            return

    if not collisions:
        print("No dual-homed skill collisions found.")
        return

    print("Dual-homed skill collisions detected:")
    has_modified_refusal = False

    for c in collisions:
        name = c["name"]
        skill_folder = c["skill_dir_name"]
        cls = c["classification"]
        skill_path = c["skills_path"]
        vendor_path = c["vendor_path"]
        print(f"\nCollision: {name}")
        print(f"  Vendor path: {vendor_path.relative_to(root_path).as_posix()}")
        print(f"  Skills path: {skill_path.relative_to(root_path).as_posix()}")
        print(f"  Classification: {cls}")

        if not args.approved:
            if cls == "identical":
                print(f"  Plan: Propose deleting duplicate folder .agents/skills/{skill_folder} and its agent links.")
                print(f"  To apply: python3 .agents/skills/extend-pipeline/scripts/refs.py dedupe --name {name} --approved")
            else:
                print(f"  Plan: Refuse automatic dedupe. Hand edits detected in {len(c['diff_files'])} file(s).")
                print("  Resolution: The user must inspect differences and decide manually.")
        else:
            if cls == "identical":
                rel_check = skill_path.relative_to(root_path).as_posix()
                if not rel_check.startswith(".agents/skills/"):
                    sys.exit(f"Safety error: Refusing to delete path outside .agents/skills: {rel_check}")

                shutil.rmtree(skill_path)
                print(f"  Removed duplicate folder: {rel_check}")
                removed_links = remove_agent_links_for_skill(root_path, skill_folder)
                for lk in removed_links:
                    print(f"  Removed agent link: {lk}")
            else:
                has_modified_refusal = True
                print(f"  ERROR: Refusing to dedupe modified collision for '{name}'.")
                print(f"  The following files differ between {vendor_path.relative_to(root_path).as_posix()} and {skill_path.relative_to(root_path).as_posix()}:")
                for rel_file, reason in c["diff_files"]:
                    print(f"    - {rel_file}: {reason}")
                    vf = vendor_path / rel_file
                    sf = skill_path / rel_file
                    if vf.is_file() and sf.is_file():
                        try:
                            v_lines = vf.read_text(encoding="utf-8", errors="ignore").splitlines()
                            s_lines = sf.read_text(encoding="utf-8", errors="ignore").splitlines()
                            diff_lines = list(difflib.unified_diff(v_lines, s_lines, fromfile=f"vendor/{rel_file}", tofile=f"skills/{rel_file}", lineterm=""))
                            if diff_lines:
                                print("      Diff preview (first 10 lines):")
                                for dl in diff_lines[:10]:
                                    print(f"        {dl}")
                        except Exception:
                            pass
                print("  Resolution: You must decide by hand whether to keep your local edits or use the vendor version.")

    if has_modified_refusal:
        sys.exit(1)


# -------------------------------------------------------------------------
# Subcommand: update
# -------------------------------------------------------------------------
def cmd_update(args):
    name = args.name
    root_path, yaml_path, lock_path = get_paths(args.root)
    ref_data = load_references(yaml_path)

    entry = next((r for r in ref_data.get("references", []) if r.get("name") == name), None)
    if not entry:
        sys.exit(f"Error: Reference '{name}' not found in .agents/references.yaml.")

    source_info = entry.get("source", {})
    url = source_info.get("url")
    subpath = source_info.get("subpath", "")
    ref = source_info.get("ref", "HEAD")

    target_dir = root_path / entry.get("path", "")
    if not target_dir.is_dir():
        sys.exit(f"Error: Target path '{target_dir}' does not exist.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        res = git_clone_or_fetch(url, ref, tmp_dir)
        if res.returncode != 0:
            sys.exit(f"Error fetching update: {res.stderr}")

        res_rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_dir, capture_output=True, text=True)
        new_commit = res_rev.stdout.strip() if res_rev.returncode == 0 else "unknown"

        fetched_skill_dir = Path(tmp_dir) / subpath if subpath else Path(tmp_dir)
        old_hashes = compute_dir_hashes(target_dir)
        new_hashes = compute_dir_hashes(fetched_skill_dir)

        added = sorted(set(new_hashes.keys()) - set(old_hashes.keys()))
        removed = sorted(set(old_hashes.keys()) - set(new_hashes.keys()))
        changed = sorted(k for k in set(old_hashes.keys()) & set(new_hashes.keys()) if old_hashes[k] != new_hashes[k])

        print(f"=== UPDATE PREVIEW FOR '{name}' ===")
        print(f"Current commit: {entry.get('pinned_commit')}")
        print(f"Upstream commit: {new_commit}")
        print(f"Changes: {len(added)} added, {len(removed)} removed, {len(changed)} changed.")
        for f in added:
            print(f"  + {f}")
        for f in removed:
            print(f"  - {f}")
        for f in changed:
            print(f"  * {f}")

        # Run vetting on new version
        print("\nRunning vetting scan on updated source...")
        vet_cmd = [sys.executable, __file__, "vet", str(fetched_skill_dir)]
        vet_res = subprocess.run(vet_cmd, capture_output=True, text=True)
        print(vet_res.stdout)

        if not args.approved:
            print("To install this update, re-run with: python3 ... refs.py update <name> --approved")
            return

        # Install update
        shutil.rmtree(target_dir)
        shutil.copytree(fetched_skill_dir, target_dir)

        entry["pinned_commit"] = new_commit
        save_references(yaml_path, ref_data)

        lock_data = load_lock(lock_path)
        lock_data[name] = {
            "commit": new_commit,
            "path": entry.get("path"),
            "files": compute_dir_hashes(target_dir)
        }
        save_lock(lock_path, lock_data)
        print(f"Successfully updated '{name}' to commit {new_commit}.")


# -------------------------------------------------------------------------
# Subcommand: remove
# -------------------------------------------------------------------------
def cmd_remove(args):
    name = args.name
    root_path, yaml_path, lock_path = get_paths(args.root)
    ref_data = load_references(yaml_path)

    entry = next((r for r in ref_data.get("references", []) if r.get("name") == name), None)
    if not entry:
        sys.exit(f"Error: Reference '{name}' not found.")

    if not args.yes:
        confirm = input(f"Are you sure you want to remove reference '{name}'? Type 'yes' to confirm: ")
        if confirm.strip() != "yes":
            print("Removal cancelled.")
            return

    target_dir = root_path / entry.get("path", "")
    if target_dir.exists():
        shutil.rmtree(target_dir)

    ref_data["references"] = [r for r in ref_data["references"] if r.get("name") != name]
    save_references(yaml_path, ref_data)

    lock_data = load_lock(lock_path)
    if name in lock_data:
        del lock_data[name]
        save_lock(lock_path, lock_data)

    print(f"Reference '{name}' and its files have been removed.")


# -------------------------------------------------------------------------
# Subcommand: restore
# -------------------------------------------------------------------------
def cmd_restore(args):
    root_path, yaml_path, lock_path = get_paths(args.root)
    ref_data = load_references(yaml_path)
    lock_data = load_lock(lock_path)

    for entry in ref_data.get("references", []):
        if entry.get("status") != "installed":
            continue

        name = entry.get("name")
        target_dir = root_path / entry.get("path", "")
        pinned_commit = entry.get("pinned_commit")
        source = entry.get("source", {})
        url = source.get("url")
        subpath = source.get("subpath", "")

        print(f"Restoring '{name}' from {url} at commit {pinned_commit}...")
        with tempfile.TemporaryDirectory() as tmp_dir:
            if os.path.isdir(url):
                skill_source = Path(url) / subpath if subpath else Path(url)
            else:
                clone_cmd = ["git", "clone", url, tmp_dir]
                res = subprocess.run(clone_cmd, capture_output=True, text=True)
                if res.returncode != 0:
                    sys.exit(f"Restore failed cloning {url}: {res.stderr}")
                if pinned_commit and pinned_commit != "unknown":
                    subprocess.run(["git", "checkout", pinned_commit], cwd=tmp_dir, capture_output=True, text=True)
                skill_source = Path(tmp_dir) / subpath if subpath else Path(tmp_dir)

            if target_dir.exists():
                shutil.rmtree(target_dir)
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(skill_source, target_dir)

    # Verify after restore
    res_v = subprocess.run([sys.executable, __file__, "verify", "--root", str(root_path)], capture_output=True, text=True)
    if res_v.returncode != 0:
        sys.exit(f"Verification failed after restore:\n{res_v.stderr}")
    print("All references restored and verified successfully.")


# -------------------------------------------------------------------------
# Subcommand: due
# -------------------------------------------------------------------------
def cmd_due(args):
    stage = args.stage
    root_path, yaml_path, _ = get_paths(args.root)
    ref_data = load_references(yaml_path)

    input_paths = [p.replace("\\", "/") for p in (args.paths or [])]
    input_keywords = set(k.lower() for k in (args.keywords or []))

    due_references = []

    for r in ref_data.get("references", []):
        if r.get("status") != "installed" or not r.get("approved"):
            continue

        used_by = r.get("used_by", [])
        if stage not in used_by:
            continue

        triggers = r.get("triggers") or {}
        trig_paths = triggers.get("paths") or []
        trig_keywords = [k.lower() for k in (triggers.get("keywords") or [])]

        # Empty triggers match always
        matched = False
        if not trig_paths and not trig_keywords:
            matched = True
        else:
            # Check path triggers
            if trig_paths and input_paths:
                for inp in input_paths:
                    for pat in trig_paths:
                        if fnmatch.fnmatch(inp, pat):
                            matched = True
                            break
                    if matched:
                        break

            # Check keyword triggers
            if not matched and trig_keywords and input_keywords:
                if any(kw in input_keywords for kw in trig_keywords):
                    matched = True

        if matched:
            rel_path = r.get("path", "")
            skill_md = os.path.join(rel_path, "SKILL.md").replace("\\", "/")
            due_references.append({
                "name": r.get("name"),
                "skill_md": skill_md,
                "mode": r.get("mode", "advisory"),
                "allow_scripts": r.get("allow_scripts", False)
            })

    for d in due_references:
        scripts_info = "true" if d["allow_scripts"] else "false"
        print(f"{d['skill_md']} (mode: {d['mode']}, allow_scripts: {scripts_info})")


# -------------------------------------------------------------------------
# Subcommand: migrate
# -------------------------------------------------------------------------
def cmd_migrate(args):
    root_path, yaml_path, _ = get_paths(args.root)
    profile_path = root_path / ".agents" / "project-profile.yaml"
    if not profile_path.is_file():
        sys.exit(f"Project profile not found at '{profile_path}'.")

    with open(profile_path, "r", encoding="utf-8") as f:
        prof = yaml.safe_load(f) or {}

    old_refs = prof.get("external_references") or []
    if not old_refs:
        print("No external_references in project profile to migrate.")
        return

    ref_data = load_references(yaml_path)
    existing_names = {r.get("name") for r in ref_data.get("references", [])}
    count = 0

    for old in old_refs:
        name = old.get("name")
        if not name or name in existing_names:
            continue
        new_entry = {
            "name": name,
            "kind": "skill",
            "category": "other",
            "purpose": old.get("purpose", ""),
            "source": {
                "type": "git",
                "url": old.get("repo", ""),
                "subpath": "",
                "ref": "HEAD"
            },
            "pinned_commit": "unknown",
            "license": "Unknown",
            "activation": "pipeline-only",
            "allow_scripts": False,
            "used_by": old.get("used_by", ["audit"]),
            "triggers": {"paths": [], "keywords": []},
            "mode": "advisory",
            "status": "declared",
            "path": old.get("path", ""),
            "approved": False
        }
        ref_data["references"].append(new_entry)
        count += 1

    save_references(yaml_path, ref_data)
    print(f"Migrated {count} reference(s) from project profile to .agents/references.yaml.")


# -------------------------------------------------------------------------
# Main CLI dispatcher
# -------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Build Forge references manager")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # fetch
    p_fetch = subparsers.add_parser("fetch")
    p_fetch.add_argument("url")
    p_fetch.add_argument("--subpath", default="")
    p_fetch.add_argument("--ref", default="HEAD")
    p_fetch.add_argument("--out", default=None)

    # vet
    p_vet = subparsers.add_parser("vet")
    p_vet.add_argument("dir")
    p_vet.add_argument("--all", action="store_true", help="Print all findings in full, including LOW")
    p_vet.add_argument("--json", action="store_true", help="Output findings as JSON")

    # add
    p_add = subparsers.add_parser("add")
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--source", required=True)
    p_add.add_argument("--source-type", default="git")
    p_add.add_argument("--subpath", default="")
    p_add.add_argument("--ref", default="HEAD")
    p_add.add_argument("--category", required=True)
    p_add.add_argument("--purpose", required=True)
    p_add.add_argument("--used-by", required=True)
    p_add.add_argument("--paths", default="")
    p_add.add_argument("--keywords", default="")
    p_add.add_argument("--mode", default="advisory")
    p_add.add_argument("--activation", default="pipeline-only")
    p_add.add_argument("--allow-scripts", action="store_true")
    p_add.add_argument("--approved", action="store_true")
    p_add.add_argument("--root", default=".")

    # list
    p_list = subparsers.add_parser("list")
    p_list.add_argument("--root", default=".")

    # verify
    p_ver = subparsers.add_parser("verify")
    p_ver.add_argument("--root", default=".")

    # update
    p_upd = subparsers.add_parser("update")
    p_upd.add_argument("name")
    p_upd.add_argument("--approved", action="store_true")
    p_upd.add_argument("--root", default=".")

    # remove
    p_rem = subparsers.add_parser("remove")
    p_rem.add_argument("name")
    p_rem.add_argument("--yes", action="store_true")
    p_rem.add_argument("--root", default=".")

    # restore
    p_res = subparsers.add_parser("restore")
    p_res.add_argument("--root", default=".")

    # due
    p_due = subparsers.add_parser("due")
    p_due.add_argument("--stage", required=True)
    p_due.add_argument("--paths", nargs="*", default=[])
    p_due.add_argument("--keywords", nargs="*", default=[])
    p_due.add_argument("--root", default=".")

    # migrate
    p_mig = subparsers.add_parser("migrate")
    p_mig.add_argument("--root", default=".")

    # dedupe
    p_ded = subparsers.add_parser("dedupe")
    p_ded.add_argument("--name", default=None)
    p_ded.add_argument("--approved", action="store_true")
    p_ded.add_argument("--root", default=".")

    args = parser.parse_args()

    handlers = {
        "fetch": cmd_fetch,
        "vet": cmd_vet,
        "add": cmd_add,
        "list": cmd_list,
        "verify": cmd_verify,
        "update": cmd_update,
        "remove": cmd_remove,
        "restore": cmd_restore,
        "due": cmd_due,
        "migrate": cmd_migrate,
        "dedupe": cmd_dedupe
    }

    handlers[args.subcommand](args)


if __name__ == "__main__":
    main()

