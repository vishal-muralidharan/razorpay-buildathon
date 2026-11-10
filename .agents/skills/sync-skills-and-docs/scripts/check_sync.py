#!/usr/bin/env python3
"""Detect drift between the project profile and the repo.

Usage: python check_sync.py --profile PATH [--root REPO_ROOT]

Checks:
  1. Layer paths and referenced files exist.
  2. Folders with files that no layer covers.
  3. Commands match the package.json scripts.
  4. Skills named in AGENTS.md exist in the skills folder.
  5. Recent commit scopes are listed in git.scopes.
  6. Installed external references exist on disk.
  7. Generated files have no edits outside custom blocks.
  8. Custom blocks do not exceed line limits.
  9. Orphan custom blocks in .agents/custom-orphans.md.
  10. Project rule runner version against package runner.
  11. Blueprint drift check.
  12. Check enforcement claims.
  13. Branch workflow state file validity.

Exit 1 on errors. Warnings are advice. Needs PyYAML (pip install pyyaml).
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

script_dir = Path(__file__).resolve().parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))
from mdscan import sections, tables

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

IGNORE = {".agents", "node_modules", "dist", "build", ".git", ".next", ".nuxt", "coverage", ".venv",
          "venv", "__pycache__", ".turbo", ".vercel", ".netlify", "target", "out"}

CONVENTION_SKILLS = {
    "build-ui",
    "maintain-design-system",
    "review-responsive-design",
    "review-directory-structure",
    "file-folder-naming",
    "review-db-structure",
}

STAMP_RE = re.compile(r"^<!-- build-forge:generated v1 body=([0-9a-f]{64}) -->\n?", re.MULTILINE)
CUSTOM_BLOCK_RE = re.compile(
    r"<!-- BEGIN CUSTOM: ([a-z0-9-]{1,40}) -->\n?(.*?)<!-- END CUSTOM: \1 -->\n?",
    re.DOTALL
)


def g(d, path, default=None):
    cur = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur if cur not in (None, "") else default


def strip_dot_slash(path: str) -> str:
    p = str(path).replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:].strip()
    return p


def path_matches(root: Path, pat: str) -> bool:
    norm = strip_dot_slash(pat).rstrip("/")
    if not norm:
        return True
    if (root / norm).exists():
        return True
    try:
        if any(root.glob(norm)):
            return True
    except Exception:
        pass
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    prof = yaml.safe_load(Path(a.profile).read_text()) or {}
    errors, warnings = [], []

    # 1. Profile paths and globs exist
    layers = [l.get("path", "").rstrip("/") for l in g(prof, "structure.layers", []) or []]
    for p in layers:
        if p and not path_matches(root, p):
            errors.append(f"layer path not found: {p}")
    for field in ("design.tokens_file", "design.enforced_by", "data.schema_source"):
        v = g(prof, field)
        if v and not path_matches(root, v):
            errors.append(f"{field} not found: {v}")
    for d in g(prof, "design.component_dirs", []) or []:
        if not path_matches(root, d):
            errors.append(f"design.component_dirs not found: {d}")
    for r in g(prof, "structure.root_allowed", []) or []:
        if r and not path_matches(root, r):
            warnings.append(f"structure.root_allowed pattern matches no files: {r}")

    # 2. Uncovered folders
    roots = sorted({p.split("/")[0] for p in layers if p})
    for r in roots:
        base = root / r
        if not base.is_dir():
            continue
        for d in sorted(x for x in base.rglob("*") if x.is_dir()):
            rel = d.relative_to(root)
            if any(part in IGNORE for part in rel.parts) or len(rel.parts) > 4:
                continue
            if not any(f.is_file() for f in d.iterdir()):
                continue
            rp = rel.as_posix()
            covered = any(rp == l or rp.startswith(l + "/") or l.startswith(rp + "/") for l in layers)
            if not covered:
                warnings.append(f"folder has files but no layer in the profile: {rp}")

    # 3. Commands vs package.json
    pkg = root / "package.json"
    if pkg.exists():
        try:
            scripts = json.loads(pkg.read_text()).get("scripts", {})
        except Exception:
            scripts = {}
            warnings.append("package.json could not be parsed")
        for key, cmd in (prof.get("commands") or {}).items():
            if not cmd or key in ("install", "test_single"):
                continue
            m = re.match(r"^(?:npm|pnpm|yarn|bun)(?: run)? ([\w:-]+)", cmd)
            if m:
                name = m.group(1)
                if name in ("install", "ci", "add", "i"):
                    continue
                if name not in scripts:
                    errors.append(f"commands.{key} runs '{name}' but package.json has no such script")

    # 4. Skills named in AGENTS.md exist
    skills_dir = root / (g(prof, "docs.skills_dir") or ".agents/skills")
    doc_scope_names = set()
    for name in (g(prof, "docs.agents_file", "AGENTS.md"), "AGENTS.generated.md"):
        f = root / name
        if not f.exists():
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        secs = sections(content)

        # Skills read ONLY from the Areas section, Skill column
        areas_lines = None
        for s in secs:
            if s["heading"].strip().lower() in ("areas", "area"):
                areas_lines = s["lines"]
                break
        if areas_lines:
            for tbl in tables(areas_lines):
                if not tbl:
                    continue
                header = [c.lower() for c in tbl[0]]
                skill_col_idx = None
                for idx, col in enumerate(header):
                    if "skill" in col:
                        skill_col_idx = idx
                        break
                if skill_col_idx is None:
                    continue
                for row in tbl[1:]:
                    if skill_col_idx >= len(row):
                        continue
                    cell = row[skill_col_idx]
                    for token in re.findall(r"`([a-z0-9-]+)`", cell):
                        if token in {"npm", "npx", "git"}:
                            continue
                        if (skills_dir / token).exists():
                            continue
                        if not (skills_dir / token / "SKILL.md").exists():
                            warnings.append(f"{name} names '{token}' but {skills_dir.relative_to(root).as_posix()}/{token}/SKILL.md is missing")

        # Scope names read ONLY from the Scope guide section
        scope_lines = None
        for s in secs:
            if s["heading"].strip().lower() in ("scope guide", "scopes", "scope"):
                scope_lines = s["lines"]
                break
        if scope_lines:
            for tbl in tables(scope_lines):
                if not tbl:
                    continue
                header = [c.lower() for c in tbl[0]]
                scope_col_idx = None
                for idx, col in enumerate(header):
                    if "scope" in col:
                        scope_col_idx = idx
                        break
                if scope_col_idx is None:
                    continue
                for row in tbl[1:]:
                    if scope_col_idx >= len(row):
                        continue
                    cell = row[scope_col_idx]
                    for token in re.findall(r"`([a-z0-9-]+)`", cell):
                        doc_scope_names.add(token)

    # 5. Commit scopes and paths validation
    raw_scopes = g(prof, "git.scopes", []) or []
    scope_names = set(doc_scope_names)
    for s in raw_scopes:
        if isinstance(s, str):
            scope_names.add(s)
        elif isinstance(s, dict) and s.get("name"):
            sname = str(s["name"])
            scope_names.add(sname)
            paths = s.get("paths") or []
            if paths:
                if not any(path_matches(root, pat) for pat in paths):
                    warnings.append(f"scope '{sname}' has paths {paths} that match no files in the repository")

    if scope_names and (root / ".git").exists():
        try:
            subs = subprocess.run(["git", "-C", str(root), "log", "-n", "50", "--pretty=%s"],
                                  capture_output=True, text=True, timeout=20).stdout.splitlines()
            used = {m.group(1) for s in subs for m in [re.match(r"^\w+\(([^)]+)\)", s)] if m}
            for s in sorted(used - scope_names):
                warnings.append(f"recent commits use scope '{s}' which is not in git.scopes")
        except Exception:
            pass

    # 6. Installed references
    for r in prof.get("external_references") or []:
        if r.get("status") == "installed" and r.get("path") and not (root / r["path"]).exists():
            errors.append(f"installed reference '{r.get('name')}' not found at {r['path']}")

    # 7 & 8. Generated files: check body hashes and custom block limits
    gen_candidates = []
    agents_f = root / (g(prof, "docs.agents_file") or "AGENTS.md")
    if agents_f.is_file():
        gen_candidates.append(agents_f)
    repo_map_f = root / (g(prof, "docs.repo_map") or ".agents/repo-map.md")
    if repo_map_f.is_file():
        gen_candidates.append(repo_map_f)
    for cskill in CONVENTION_SKILLS:
        cf = skills_dir / cskill / "SKILL.md"
        if cf.is_file():
            gen_candidates.append(cf)

    for gf in gen_candidates:
        txt = gf.read_text(encoding="utf-8").replace("\r\n", "\n")
        sm = STAMP_RE.search(txt)
        rel_label = gf.relative_to(root).as_posix()
        if sm:
            stamp_h = sm.group(1)
            clean = STAMP_RE.sub("", txt)
            clean = CUSTOM_BLOCK_RE.sub("", clean)
            body_h = hashlib.sha256(clean.encode("utf-8")).hexdigest()
            if body_h != stamp_h:
                errors.append(f"generated file '{rel_label}' has edits outside custom blocks (run render.py --salvage or --force)")

        # Check block limits
        total_custom = 0
        for m in CUSTOM_BLOCK_RE.finditer(txt):
            bname = m.group(1)
            bcontent = m.group(2)
            lines = len(bcontent.splitlines())
            total_custom += lines
            if bname in ("salvaged", "legacy"):
                warnings.append(f"custom block '{bname}' in '{rel_label}' needs review (merge or remove)")
            if lines > 160:
                errors.append(f"custom block '{bname}' in '{rel_label}' has {lines} lines (> 160; facts belong in blueprints or profile)")
            elif lines > 80:
                warnings.append(f"custom block '{bname}' in '{rel_label}' has {lines} lines (> 80; facts belong in blueprints or profile)")

        if total_custom > 600:
            errors.append(f"file '{rel_label}' has {total_custom} total custom lines (> 600; facts belong in blueprints or profile)")
        elif total_custom > 300:
            warnings.append(f"file '{rel_label}' has {total_custom} total custom lines (> 300; facts belong in blueprints or profile)")

    # 9. Orphan custom blocks
    orphans_f = root / ".agents" / "custom-orphans.md"
    if orphans_f.is_file():
        otxt = orphans_f.read_text(encoding="utf-8")
        if "<!-- BEGIN CUSTOM:" in otxt:
            warnings.append("orphan custom blocks exist in .agents/custom-orphans.md (review and merge or remove)")

    # 10. Check runner version
    proj_runner = root / ".agents" / "checks" / "run_rule_checks.py"
    pkg_runner = root / ".agents" / "skills" / "rules-to-tests" / "scripts" / "run_rule_checks.py"
    if proj_runner.is_file() and pkg_runner.is_file():
        def extract_runner_version(fpath):
            m = re.search(r"^RUNNER_VERSION\s*=\s*(\d+)", fpath.read_text(encoding="utf-8", errors="ignore"), re.MULTILINE)
            return int(m.group(1)) if m else 0
        pv = extract_runner_version(proj_runner)
        kv = extract_runner_version(pkg_runner)
        if pv < kv:
            warnings.append(f".agents/checks/run_rule_checks.py has runner version {pv}, older than {kv} in rules-to-tests (refresh recommended)")

    # 11. Blueprint drift check
    bp_script = root / ".agents" / "skills" / "project-blueprints" / "scripts" / "blueprint.py"
    if not bp_script.is_file():
        alt_bp = Path(__file__).resolve().parents[3] / "skills" / "project-blueprints" / "scripts" / "blueprint.py"
        if alt_bp.is_file():
            bp_script = alt_bp

    bp_dir = root / ".agents" / "blueprints"
    if bp_script.is_file():
        if bp_dir.is_dir():
            res = subprocess.run([sys.executable, "-B", str(bp_script), "drift", "--root", str(root)], capture_output=True, text=True)
            if res.returncode != 0:
                for line in (res.stderr or res.stdout).splitlines():
                    if line.startswith("DRIFT ERROR:") or line.startswith("LINK-CHECK ERROR:") or "Stale blueprint areas:" in line:
                        warnings.append(line.strip())
                if not any("DRIFT" in w or "LINK-CHECK" in w or "Stale" in w for w in warnings):
                    warnings.append("blueprint drift detected (run blueprint.py drift)")
    else:
        print("NOTE  project-blueprints skill not installed; skipping blueprint drift check")

    # 12. Check enforcement claims
    for r in prof.get("rules") or []:
        rid = r.get("id", "unknown")
        enforced = r.get("enforced_by", "manual")
        if enforced in ("test", "lint"):
            has_check = r.get("check") is not None
            e_ref = r.get("enforced_by_ref")
            has_ref = e_ref is not None and bool(e_ref.get("file"))
            is_design_covered = False
            des_enf = prof.get("design", {}).get("enforced_by")
            if r.get("area") in ("design", "tokens") and des_enf:
                des_file = root / strip_dot_slash(des_enf)
                if des_file.is_file():
                    try:
                        if f"[{rid}]" in des_file.read_text(encoding="utf-8", errors="ignore"):
                            is_design_covered = True
                    except Exception:
                        pass
            if not (has_check or has_ref or is_design_covered):
                warnings.append(f"claim-unverified: rule {rid} claims {enforced} enforcement without check or enforced_by_ref")

    # 13. Check branch workflow state file
    state_file = root / ".agents" / "work" / "branch-state.json"
    if state_file.is_file():
        try:
            sdata = json.loads(state_file.read_text(encoding="utf-8"))
            sbranch = sdata.get("branch")
            if sbranch and (root / ".git").exists():
                res_b = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", f"refs/heads/{sbranch}"],
                                       capture_output=True, text=True)
                if res_b.returncode != 0:
                    warnings.append(f"branch state file records branch '{sbranch}' which no longer exists in git")
        except Exception:
            warnings.append("corrupted branch state file in .agents/work/branch-state.json")

    for w in sorted(set(warnings)):
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"\n{len(errors)} error(s), {len(set(warnings))} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
