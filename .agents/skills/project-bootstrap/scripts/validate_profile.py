#!/usr/bin/env python3
"""Validate .agents/project-profile.yaml.

Usage: python validate_profile.py --profile PATH [--root REPO_ROOT] [--strict]

Exit 0 when there are no errors. Exit 1 otherwise.
Unresolved "TODO" values are warnings. With --strict they are errors.
Needs PyYAML (pip install pyyaml).
"""
import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

AREAS = {"design", "tokens", "motion", "responsive", "structure", "naming", "data",
         "security", "verify", "git", "docs", "process"}
STAGES = {"audit", "plan", "build", "verify", "deploy", "commit", "docs", "report"}
REF_STAGES = {"audit", "build", "verify", "deploy", "report"}
REF_MODES = {"advisory", "gate"}
REF_ACTIVATIONS = {"pipeline-only", "native"}
REF_CATEGORIES = {"backend", "database", "security", "deploy", "hosting", "browser", "performance", "accessibility", "other"}
ENFORCED = {"manual", "test", "lint", "check"}
STATUS = {"declared", "installed", "rejected"}
PUSH = {"never", "ask", "allowed"}
SUPPORTED_SCHEMA_VERSIONS = (1, 2)
MODES = {"existing", "new"}
RULE_KEYS = {"id", "area", "text", "enforced_by", "check", "evidence", "exceptions", "pack", "enforced_by_ref"}
CHECK_TYPES = {"forbid", "require_file", "forbid_file", "root_only", "no_dual_homed_skills"}
CHECK_KEYS = {"type", "pattern", "include", "exclude", "path", "examples", "hint"}
KNOWN_PACKS = {"web-hazards", "native-controls"}
NAMING_KEYS = {"item", "style", "example"}
LAYER_KEYS = {"path", "purpose"}
BP_KEYS = {"from", "layout"}
SCOPE_KEYS = {"name", "purpose", "paths"}


def stray(entry, allowed):
    return sorted(str(k) for k in entry if k not in allowed or entry[k] is None)


def get(d, path, default=None):
    cur = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def todos(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from todos(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from todos(v, f"{path}[{i}]")
    elif isinstance(node, str) and node.strip().upper().startswith("TODO"):
        yield path


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
    ap.add_argument("--root", default=None)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--strict-paths", action="store_true", help="Treat unmatched paths and globs as errors.")
    ap.add_argument("--strict-claims", action="store_true", help="Treat claim-unverified warnings as errors.")
    a = ap.parse_args()

    errors, warnings = [], []
    try:
        prof = yaml.safe_load(Path(a.profile).read_text())
    except Exception as e:
        sys.exit(f"ERROR: cannot read profile: {e}")
    if not isinstance(prof, dict):
        sys.exit("ERROR: profile must be a YAML mapping")

    if prof.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(f"schema_version must be one of {list(SUPPORTED_SCHEMA_VERSIONS)}")

    for path in ("project.name", "project.summary", "stack.language", "stack.framework", "stack.package_manager"):
        if not get(prof, path):
            errors.append(f"{path} is required")
    if get(prof, "project.mode") not in MODES:
        errors.append("project.mode must be existing or new")

    cmds = get(prof, "commands", {}) or {}
    if not cmds.get("check") and not all(cmds.get(k) for k in ("lint", "test", "build")):
        errors.append("commands.check is required, or set lint, test and build")
    if "{path}" not in (cmds.get("test_single") or "{path}"):
        warnings.append("commands.test_single should contain {path}")

    layers = get(prof, "structure.layers", [])
    if not layers:
        errors.append("structure.layers needs at least 1 entry")
    for i, l in enumerate(layers or []):
        if not isinstance(l, dict) or not l.get("path") or not l.get("purpose"):
            errors.append(f"structure.layers[{i}] needs path and purpose")
        elif stray(l, LAYER_KEYS):
            errors.append(f"structure.layers[{i}] has unexpected keys {stray(l, LAYER_KEYS)}. Quote values that contain commas.")
    if get(prof, "structure.tests") not in ("colocated", "tests-dir"):
        errors.append("structure.tests must be colocated or tests-dir")

    for i, n in enumerate(prof.get("naming") or []):
        if not isinstance(n, dict) or not all(n.get(k) for k in ("item", "style", "example")):
            errors.append(f"naming[{i}] needs item, style and example")
        elif stray(n, NAMING_KEYS):
            errors.append(f"naming[{i}] has unexpected keys {stray(n, NAMING_KEYS)}. Quote values that contain commas.")

    if get(prof, "design.enabled") and not get(prof, "design.tokens_file"):
        errors.append("design.tokens_file is required when design.enabled is true")
    if get(prof, "responsive.enabled"):
        lo, hi = get(prof, "responsive.min_width", 0), get(prof, "responsive.max_width", 0)
        if not (isinstance(lo, int) and isinstance(hi, int) and 0 < lo < hi):
            errors.append("responsive.min_width must be less than responsive.max_width")

    for i, b in enumerate(get(prof, "responsive.breakpoints", []) or []):
        if not isinstance(b, dict) or not isinstance(b.get("from"), int) or not b.get("layout") or stray(b, BP_KEYS):
            errors.append(f"responsive.breakpoints[{i}] needs an integer from and a layout string. Quote values that contain commas.")

    if get(prof, "git.push") not in PUSH:
        errors.append("git.push must be never, ask or allowed")
    if not get(prof, "git.commit_format"):
        errors.append("git.commit_format is required")

    # git.workflow profile configuration
    wf = get(prof, "git.workflow")
    if "workflow" in (get(prof, "git") or {}):
        pass
    if wf is not None:
        if not isinstance(wf, dict):
            errors.append("git.workflow must be a mapping")
        else:
            WORKFLOW_KEYS = {"default_branch", "mode", "branch_format", "sync", "merge_method", "remote", "cleanup", "worktree"}
            if stray(wf, WORKFLOW_KEYS):
                errors.append(f"git.workflow has unexpected keys {stray(wf, WORKFLOW_KEYS)}")

            d_branch = wf.get("default_branch")
            if d_branch is not None:
                if not isinstance(d_branch, str) or not d_branch.strip():
                    errors.append("git.workflow.default_branch must be a non-empty string")

            mode = wf.get("mode")
            if mode is not None and mode not in ("off", "ask", "always"):
                errors.append("git.workflow.mode must be off, ask or always")

            b_format = wf.get("branch_format")
            if b_format is not None:
                if not isinstance(b_format, str) or not b_format.strip():
                    errors.append("git.workflow.branch_format must be a non-empty string")

            sync = wf.get("sync")
            if sync is not None and sync not in ("rebase", "merge"):
                errors.append("git.workflow.sync must be rebase or merge")

            m_method = wf.get("merge_method")
            if m_method is not None and m_method not in ("squash", "merge", "rebase"):
                errors.append("git.workflow.merge_method must be squash, merge or rebase")

            remote = wf.get("remote")
            if remote is not None:
                if not isinstance(remote, str) or not remote.strip():
                    errors.append("git.workflow.remote must be a non-empty string")

            cleanup = wf.get("cleanup")
            if cleanup is not None and cleanup not in ("ask", "keep"):
                errors.append("git.workflow.cleanup must be ask or keep")

            worktree = wf.get("worktree")
            if worktree is not None and not isinstance(worktree, bool):
                errors.append("git.workflow.worktree must be a boolean")

    scopes = get(prof, "git.scopes")
    if scopes is not None:
        if not isinstance(scopes, list):
            errors.append("git.scopes must be a list")
        else:
            seen_scope_names = set()
            for idx, sc in enumerate(scopes):
                if isinstance(sc, str):
                    sname = sc
                    if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", sname):
                        errors.append(f"git.scopes[{idx}] '{sname}' must be kebab-case")
                    if sname in seen_scope_names:
                        errors.append(f"duplicate scope name: {sname}")
                    seen_scope_names.add(sname)
                elif isinstance(sc, dict):
                    if stray(sc, SCOPE_KEYS):
                        errors.append(f"git.scopes[{idx}] has unexpected keys {stray(sc, SCOPE_KEYS)}")
                    sname = sc.get("name")
                    if sname is None or not isinstance(sname, str) or not sname.strip():
                        errors.append(f"git.scopes[{idx}].name must be a non-empty string")
                    else:
                        if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", sname):
                            errors.append(f"git.scopes[{idx}].name '{sname}' must be kebab-case")
                        if sname in seen_scope_names:
                            errors.append(f"duplicate scope name: {sname}")
                        seen_scope_names.add(sname)

                    purpose = sc.get("purpose")
                    if purpose is not None:
                        if not isinstance(purpose, str):
                            errors.append(f"git.scopes[{idx}].purpose must be a string")
                        elif len(purpose) > 100:
                            errors.append(f"git.scopes[{idx}].purpose exceeds 100 characters ({len(purpose)} chars)")

                    paths = sc.get("paths")
                    if paths is not None:
                        if not isinstance(paths, list):
                            errors.append(f"git.scopes[{idx}].paths must be a list")
                        else:
                            for pidx, pat in enumerate(paths):
                                if not isinstance(pat, str) or not pat.strip():
                                    errors.append(f"git.scopes[{idx}].paths[{pidx}] must be a non-empty string")
                                elif pat.count("[") != pat.count("]") or "\x00" in pat:
                                    errors.append(f"git.scopes[{idx}].paths[{pidx}] '{pat}' is not a valid glob")
                else:
                    errors.append(f"git.scopes[{idx}] must be a string or a mapping")

    names = set()
    root_path = Path(a.root).resolve() if a.root else Path(".").resolve()
    ref_yaml = root_path / ".agents" / "references.yaml"

    if ref_yaml.is_file():
        try:
            rdata = yaml.safe_load(ref_yaml.read_text(encoding="utf-8")) or {}
        except Exception as e:
            errors.append(f"Invalid YAML in .agents/references.yaml: {e}")
            rdata = {}

        if not isinstance(rdata, dict):
            errors.append(".agents/references.yaml must be a mapping")
        else:
            if rdata.get("schema_version") != 1:
                errors.append(".agents/references.yaml schema_version must be 1")
            if not isinstance(rdata.get("vendor_in_git", False), bool):
                errors.append(".agents/references.yaml vendor_in_git must be a boolean")

            ref_entries = rdata.get("references")
            if not isinstance(ref_entries, list):
                errors.append(".agents/references.yaml 'references' must be a list")
            else:
                for idx, entry in enumerate(ref_entries):
                    if not isinstance(entry, dict):
                        errors.append(f"references[{idx}] must be a mapping")
                        continue
                    rname = entry.get("name")
                    if not rname or not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", str(rname)):
                        errors.append(f"references[{idx}].name '{rname}' must be kebab-case")
                    if rname in names:
                        errors.append(f"references[{idx}].name '{rname}' is a duplicate")
                    names.add(rname)

                    if entry.get("kind") != "skill":
                        errors.append(f"references[{idx}].kind must be 'skill'")
                    if entry.get("category") not in REF_CATEGORIES:
                        errors.append(f"references[{idx}].category must be one of {sorted(REF_CATEGORIES)}")
                    if entry.get("status") not in STATUS:
                        errors.append(f"references[{idx}].status must be one of {sorted(STATUS)}")
                    if entry.get("mode") not in REF_MODES:
                        errors.append(f"references[{idx}].mode must be one of {sorted(REF_MODES)}")
                    if entry.get("activation") not in REF_ACTIVATIONS:
                        errors.append(f"references[{idx}].activation must be one of {sorted(REF_ACTIVATIONS)}")

                    used = entry.get("used_by") or []
                    if not isinstance(used, list) or not used or (set(used) - REF_STAGES):
                        errors.append(f"references[{idx}].used_by must list stages from {sorted(REF_STAGES)}")

                    if entry.get("status") == "installed":
                        rpath = entry.get("path")
                        if not rpath:
                            errors.append(f"references[{idx}].path is required when installed")
                        else:
                            norm_path = Path(rpath).as_posix()
                            if not (norm_path.startswith(".agents/vendor/") or norm_path.startswith(".agents/skills/")):
                                errors.append(f"references[{idx}].path '{rpath}' must be inside .agents/vendor or .agents/skills")
                            elif a.root and not (root_path / rpath).exists():
                                if rdata.get("vendor_in_git", False) is False and norm_path.startswith(".agents/vendor/"):
                                    warnings.append(f"references[{idx}].path not found (run refs.py restore): {rpath}")
                                else:
                                    errors.append(f"references[{idx}].path not found: {rpath}")
                        if not entry.get("pinned_commit") or entry.get("pinned_commit") == "unknown":
                            errors.append(f"references[{idx}].pinned_commit is required when installed")
                        if entry.get("approved") is not True:
                            errors.append(f"references[{idx}].approved must be true when installed")

    # Backwards compatibility: external_references in profile
    old_refs = prof.get("external_references")
    if old_refs is not None:
        warnings.append("`external_references` in project profile is deprecated. Use .agents/references.yaml instead.")
        if isinstance(old_refs, list):
            for i, r in enumerate(old_refs):
                if not isinstance(r, dict):
                    errors.append(f"external_references[{i}] must be a mapping")
                    continue
                name = r.get("name")
                if not name:
                    errors.append(f"external_references[{i}].name is required")
                names.add(name)
                repo = str(r.get("repo", ""))
                if not (repo.startswith("https://") or repo.startswith("git@")):
                    errors.append(f"external_references[{i}].repo must be an https or git URL")
                if r.get("status") not in STATUS:
                    errors.append(f"external_references[{i}].status must be one of {sorted(STATUS)}")
                bad = set(r.get("used_by") or []) - STAGES
                if bad or not r.get("used_by"):
                    errors.append(f"external_references[{i}].used_by must list stages from {sorted(STAGES)}")
                if r.get("status") == "installed":
                    if not r.get("path"):
                        errors.append(f"external_references[{i}].path is required when installed")
                    elif a.root and not (Path(a.root) / r["path"]).exists():
                        errors.append(f"external_references[{i}].path not found: {r['path']}")

    for cap, cfg in (prof.get("capabilities") or {}).items():
        if not isinstance(cfg, dict):
            errors.append(f"capabilities.{cap} must be a mapping")
            continue
        ref = cfg.get("reference")
        if ref and ref not in names:
            errors.append(f"capabilities.{cap}.reference '{ref}' is not in .agents/references.yaml")
        if cap == "deploy":
            if cfg.get("enabled") and not (cfg.get("command") or cmds.get("deploy")):
                errors.append("capabilities.deploy is enabled but has no command")
            if cfg.get("on_failure", "report") not in ("report", "self-heal"):
                errors.append("capabilities.deploy.on_failure must be report or self-heal")
            ma = cfg.get("max_attempts", 3)
            if not (isinstance(ma, int) and 1 <= ma <= 10):
                errors.append("capabilities.deploy.max_attempts must be an integer from 1 to 10")

    bp = prof.get("blueprints")
    if bp is not None:
        if not isinstance(bp, dict):
            errors.append("blueprints must be a mapping")
        else:
            bad_bp = sorted(set(bp) - {"enabled", "dir", "areas"})
            if bad_bp:
                errors.append(f"blueprints has unexpected keys: {bad_bp}")
            if "enabled" in bp and not isinstance(bp["enabled"], bool):
                errors.append("blueprints.enabled must be a boolean")
            if "dir" in bp and not isinstance(bp["dir"], str):
                errors.append("blueprints.dir must be a string")
            if "areas" in bp and not isinstance(bp["areas"], list):
                errors.append("blueprints.areas must be a list of strings")

    # Prohibit storing raw lists of keys or tokens in the profile
    for banned_path in ("tokens", "keys", "data.storage_keys", "data.keys", "design.tokens", "blueprints.tokens", "blueprints.keys"):
        val = get(prof, banned_path)
        if isinstance(val, (list, dict)):
            errors.append(f"Do not store lists of keys or tokens in profile ({banned_path}). Facts belong in blueprints.")

    # Discover packaged rule packs
    script_dir = Path(__file__).resolve().parent
    packaged_packs_dir = script_dir.parent / "references" / "rule-packs"
    packaged_packs = {}
    if packaged_packs_dir.is_dir():
        for yf in packaged_packs_dir.glob("*.yaml"):
            try:
                ydata = yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
                if isinstance(ydata, dict) and "id" in ydata and "version" in ydata:
                    packaged_packs[ydata["id"]] = ydata["version"]
            except Exception:
                pass

    rule_packs = prof.get("rule_packs")
    if rule_packs is not None:
        if not isinstance(rule_packs, list):
            errors.append("rule_packs must be a list")
        else:
            for rpidx, rp in enumerate(rule_packs):
                if not isinstance(rp, dict):
                    errors.append(f"rule_packs[{rpidx}] must be a mapping")
                    continue
                pid = rp.get("id")
                pver = rp.get("version")
                if not pid or not isinstance(pid, str):
                    errors.append(f"rule_packs[{rpidx}].id is required")
                if pver is None or not isinstance(pver, int):
                    errors.append(f"rule_packs[{rpidx}].version is required and must be an integer")
                if pid and packaged_packs:
                    if pid not in packaged_packs:
                        warnings.append(f"rule_packs[{rpidx}] unknown pack id '{pid}'")
                    elif isinstance(pver, int) and pver < packaged_packs[pid]:
                        warnings.append(
                            f"rule_packs[{rpidx}] pack '{pid}' version {pver} is older than packaged version {packaged_packs[pid]}"
                        )

    dropped_rules = prof.get("dropped_pack_rules")
    if dropped_rules is not None:
        if not isinstance(dropped_rules, list):
            errors.append("dropped_pack_rules must be a list of rule ids")
        else:
            for dridx, dr in enumerate(dropped_rules):
                if not isinstance(dr, str) or not dr.strip():
                    errors.append(f"dropped_pack_rules[{dridx}] must be a non-empty string rule id")

    ids = set()
    for i, r in enumerate(prof.get("rules") or []):
        if not isinstance(r, dict):
            errors.append(f"rules[{i}] must be a mapping")
            continue
        rid = r.get("id")
        if not rid:
            errors.append(f"rules[{i}].id is required")
        elif rid in ids:
            errors.append(f"duplicate rule id: {rid}")
        ids.add(rid)
        if r.get("area") not in AREAS:
            errors.append(f"rules[{i}] ({rid}) area must be one of {sorted(AREAS)}")
        if not r.get("text"):
            errors.append(f"rules[{i}] ({rid}) text is required")
        if r.get("enforced_by", "manual") not in ENFORCED:
            errors.append(f"rules[{i}] ({rid}) enforced_by must be one of {sorted(ENFORCED)}")
        if stray(r, RULE_KEYS):
            errors.append(f"rules[{i}] ({rid}) has unexpected keys {stray(r, RULE_KEYS)}. Quote text that contains commas.")
        ev = r.get("evidence")
        if ev is not None:
            if isinstance(ev, str):
                ev_list = [ev]
            elif isinstance(ev, list):
                ev_list = ev
            else:
                errors.append(f"rules[{i}] ({rid}) evidence must be a string or list of paths")
                ev_list = []
            if a.root:
                root_path = Path(a.root)
                for ep in ev_list:
                    ep_clean = str(ep).split(":")[0].strip()
                    ep_norm = strip_dot_slash(ep_clean)
                    if ep_norm and not (root_path / ep_norm).exists():
                        warnings.append(f"rule {rid} evidence path does not exist: '{ep}'")
        exc = r.get("exceptions")
        if exc is not None:
            if not isinstance(exc, list):
                errors.append(f"rules[{i}] ({rid}) exceptions must be a list")
            else:
                for xidx, item in enumerate(exc):
                    if not isinstance(item, dict):
                        errors.append(f"rules[{i}] ({rid}) exceptions[{xidx}] must be a mapping with path and reason")
                        continue
                    epath = item.get("path")
                    reason = item.get("reason")
                    if not epath or not isinstance(epath, str):
                        errors.append(f"rules[{i}] ({rid}) exceptions[{xidx}].path is required")
                    if not reason or not isinstance(reason, str) or not reason.strip():
                        errors.append(f"rules[{i}] ({rid}) exceptions[{xidx}].reason is required and non-empty")
                    if a.root and epath and isinstance(epath, str):
                        root_path = Path(a.root)
                        norm_epath = strip_dot_slash(epath)
                        if not path_matches(root_path, norm_epath):
                            warnings.append(f"rule {rid} exception path matches no file: '{epath}'")
        rpack = r.get("pack")
        if rpack is not None:
            if not isinstance(rpack, str) or not re.match(r"^[a-z0-9-]+@\d+$", rpack):
                errors.append(f"rules[{i}] ({rid}) pack '{rpack}' must be in format <id>@<version>")
        e_ref = r.get("enforced_by_ref")
        if e_ref is not None:
            if not isinstance(e_ref, dict):
                errors.append(f"rules[{i}] ({rid}) enforced_by_ref must be a mapping")
            else:
                bad_ref_keys = sorted(set(e_ref) - {"file", "contains"})
                if bad_ref_keys:
                    errors.append(f"rules[{i}] ({rid}) enforced_by_ref has unexpected keys: {bad_ref_keys}")
                if not e_ref.get("file") or not isinstance(e_ref["file"], str):
                    errors.append(f"rules[{i}] ({rid}) enforced_by_ref.file is required")
        chk = r.get("check")
        if chk is not None:
            if isinstance(chk, str):
                if chk not in CHECK_TYPES:
                    errors.append(f"rules[{i}] ({rid}) check must be one of {sorted(CHECK_TYPES)}")
            elif not isinstance(chk, dict) or chk.get("type") not in CHECK_TYPES:
                errors.append(f"rules[{i}] ({rid}) check.type must be one of {sorted(CHECK_TYPES)}")
            else:
                bad_keys = sorted(set(chk) - CHECK_KEYS)
                if bad_keys:
                    errors.append(f"rules[{i}] ({rid}) check has unexpected keys {bad_keys}")
                t = chk["type"]
                if t == "forbid":
                    try:
                        re.compile(str(chk.get("pattern", "")))
                    except re.error as e:
                        errors.append(f"rules[{i}] ({rid}) check.pattern is not a valid regex: {e}")
                    if not chk.get("pattern"):
                        errors.append(f"rules[{i}] ({rid}) check.pattern is required for forbid")
                if t in ("forbid", "forbid_file") and not chk.get("include"):
                    errors.append(f"rules[{i}] ({rid}) check.include needs at least 1 glob")
                if t == "require_file" and not chk.get("path"):
                    errors.append(f"rules[{i}] ({rid}) check.path is required for require_file")
                if t == "root_only" and not get(prof, "structure.root_allowed"):
                    errors.append(f"rules[{i}] ({rid}) root_only needs structure.root_allowed")
                if "examples" in chk:
                    exs = chk["examples"]
                    if not isinstance(exs, dict):
                        errors.append(f"rules[{i}] ({rid}) check.examples must be a mapping with bad and good lists")
                    else:
                        for ek in ("bad", "good"):
                            if ek in exs and not isinstance(exs[ek], list):
                                errors.append(f"rules[{i}] ({rid}) check.examples.{ek} must be a list of strings")
                if "hint" in chk and not isinstance(chk["hint"], str):
                    errors.append(f"rules[{i}] ({rid}) check.hint must be a string")
            if r.get("enforced_by") != "test":
                warnings.append(f"rule {rid} has a check, so enforced_by should be test")
        claim_issue = errors.append if a.strict_claims else warnings.append
        enforced = r.get("enforced_by", "manual")
        if enforced in ("test", "lint"):
            has_check = chk is not None
            has_ref = e_ref is not None and bool(e_ref.get("file"))
            is_design_covered = False
            design_enforced_by = get(prof, "design.enforced_by")
            if r.get("area") in ("design", "tokens") and design_enforced_by:
                if a.root:
                    des_file = root_path / strip_dot_slash(design_enforced_by)
                    if des_file.is_file():
                        try:
                            if f"[{rid}]" in des_file.read_text(encoding="utf-8", errors="ignore"):
                                is_design_covered = True
                        except Exception:
                            pass
                else:
                    is_design_covered = True

            if not (has_check or has_ref or is_design_covered):
                claim_issue(f"claim-unverified: rule {rid} claims {enforced} enforcement without check or enforced_by_ref")

            if a.root and has_ref:
                ref_file_rel = strip_dot_slash(e_ref["file"])
                ref_file = root_path / ref_file_rel
                if not ref_file.exists():
                    claim_issue(f"rule {rid} enforced_by_ref file not found: '{e_ref['file']}'")
                else:
                    expected_contains = e_ref.get("contains") or f"[{rid}]"
                    try:
                        f_text = ref_file.read_text(encoding="utf-8", errors="ignore")
                        if expected_contains not in f_text:
                            claim_issue(f"rule {rid} enforced_by_ref file '{e_ref['file']}' does not contain '{expected_contains}'")
                    except Exception as ex:
                        claim_issue(f"rule {rid} cannot read enforced_by_ref file '{e_ref['file']}': {ex}")

    for field in ("docs.skills_dir", "docs.agents_file", "docs.repo_map"):
        if not get(prof, field):
            errors.append(f"{field} is required")

    if a.root:
        root_dir = Path(a.root).resolve()
        record_issue = errors.append if a.strict_paths else warnings.append

        # 1. structure.layers
        for idx, l in enumerate(get(prof, "structure.layers", []) or []):
            if isinstance(l, dict) and l.get("path"):
                lpath = l["path"]
                if not path_matches(root_dir, lpath):
                    record_issue(f"unmatched path in structure.layers[{idx}]: '{lpath}'")

        # 2. design.component_dirs
        for idx, d in enumerate(get(prof, "design.component_dirs", []) or []):
            if isinstance(d, str) and d:
                if not path_matches(root_dir, d):
                    record_issue(f"unmatched path in design.component_dirs[{idx}]: '{d}'")

        # 3. git.scopes[].paths
        for sidx, sc in enumerate(get(prof, "git.scopes", []) or []):
            if isinstance(sc, dict):
                sname = sc.get("name", str(sidx))
                for pidx, pat in enumerate(sc.get("paths", []) or []):
                    if isinstance(pat, str) and pat:
                        if not path_matches(root_dir, pat):
                            record_issue(f"unmatched path in git.scopes[{sname}].paths[{pidx}]: '{pat}'")

        # 4. structure.root_allowed
        for idx, r in enumerate(get(prof, "structure.root_allowed", []) or []):
            if isinstance(r, str) and r:
                if not path_matches(root_dir, r):
                    record_issue(f"unmatched pattern in structure.root_allowed[{idx}]: '{r}'")

        # 5. data.schema_source
        ss = get(prof, "data.schema_source")
        if ss and isinstance(ss, str) and not path_matches(root_dir, ss):
            record_issue(f"unmatched path in data.schema_source: '{ss}'")

        # 6. design.tokens_file
        tf = get(prof, "design.tokens_file")
        if tf and isinstance(tf, str) and not path_matches(root_dir, tf):
            record_issue(f"unmatched path in design.tokens_file: '{tf}'")

    unresolved = list(todos(prof))
    for p in unresolved:
        (errors if a.strict else warnings).append(f"unresolved TODO at {p}")

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s), {len(unresolved)} unresolved TODO(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
