#!/usr/bin/env python3
"""Rule pack management CLI for Build Forge.

Usage: python packs.py {list,show,plan,apply,diff,lint} ...

Commands:
  list                  List available rule packs.
  show <id>             Show details of a rule pack.
  plan <id>             Show proposed changes against a project profile.
  apply <id>            Apply pack rules to a project profile.
  diff <id>             Compare installed pack rules against the packaged version.
  lint                  Validate all rule packs against schema and test checks.
"""
import argparse
import copy
import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

VALID_AREAS = {
    "design", "tokens", "motion", "responsive", "structure", "naming",
    "data", "security", "verify", "git", "docs", "process"
}
IGNORE_DIRS = {
    "node_modules", "dist", "build", ".git", ".next", ".nuxt", "coverage",
    ".venv", "venv", "__pycache__", ".turbo", ".vercel", ".netlify", "target", "out"
}
MAX_BYTES = 1_000_000


def get_packs_dir(custom_dir = None) -> Path:
    if custom_dir:
        return Path(custom_dir).resolve()
    script_dir = Path(__file__).resolve().parent
    return script_dir.parent / "references" / "rule-packs"


def load_all_packs(packs_dir: Path) -> dict:
    packs = {}
    if not packs_dir.is_dir():
        return packs
    for f in sorted(packs_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict) and "id" in data:
                packs[data["id"]] = data
        except Exception:
            pass
    return packs


def load_pack(pack_id: str, packs_dir: Path) -> dict:
    pack_file = packs_dir / f"{pack_id}.yaml"
    if not pack_file.is_file():
        sys.exit(f"Rule pack not found: {pack_id}")
    try:
        data = yaml.safe_load(pack_file.read_text(encoding="utf-8")) or {}
    except Exception as e:
        sys.exit(f"Error loading pack '{pack_id}': {e}")
    if not isinstance(data, dict) or "id" not in data:
        sys.exit(f"Invalid pack schema in '{pack_file}'")
    return data


def expand_braces(pattern):
    m = re.search(r"\{([^{}]*)\}", pattern)
    if not m:
        return [pattern]
    out = []
    for option in m.group(1).split(","):
        out += expand_braces(pattern[:m.start()] + option + pattern[m.end():])
    return out


def glob_to_regex(glob):
    i, out = 0, ""
    while i < len(glob):
        c = glob[i]
        if glob.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif glob.startswith("**", i):
            out += ".*"
            i += 2
        elif c == "*":
            out += "[^/]*"
            i += 1
        elif c == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(c)
            i += 1
    return re.compile("^" + out + "$")


def compile_globs(globs):
    regexes = []
    for g in globs or []:
        for expanded in expand_braces(g):
            regexes.append(glob_to_regex(expanded))
    return regexes


def matching_files(files, include, exclude):
    inc, exc = compile_globs(include), compile_globs(exclude)
    return [f for f in files if any(r.match(f) for r in inc) and not any(r.match(f) for r in exc)]


def list_repo_files(root: Path):
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for name in filenames:
            rel = Path(dirpath, name).relative_to(root).as_posix()
            files.append(rel)
    return sorted(files)


def probe_rule_violations(rule: dict, root: Path, files: list) -> list:
    chk = rule.get("check")
    if not isinstance(chk, dict):
        return []
    t = chk.get("type")
    problems = []
    excludes = list(chk.get("exclude") or [])
    for exc in rule.get("exceptions", []) or []:
        if isinstance(exc, dict) and exc.get("path"):
            excludes.append(exc["path"])
        elif isinstance(exc, str):
            excludes.append(exc)

    if t == "forbid":
        try:
            rx = re.compile(chk["pattern"])
        except re.error:
            return problems
        for rel in matching_files(files, chk.get("include"), excludes):
            p = root / rel
            try:
                if p.stat().st_size > MAX_BYTES:
                    continue
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for line_idx, line in enumerate(text.splitlines(), 1):
                m = rx.search(line)
                if m:
                    match_snippet = m.group(0).strip()
                    if len(match_snippet) > 50:
                        match_snippet = match_snippet[:47] + "..."
                    problems.append({
                        "file": rel,
                        "line": line_idx,
                        "match": match_snippet
                    })
    elif t == "forbid_file":
        for rel in matching_files(files, chk.get("include"), excludes):
            problems.append({
                "file": rel,
                "line": 1,
                "match": "Forbidden file exists"
            })
    return problems


def expand_rule_variables(rule: dict, component_dirs: list) -> tuple:
    rule_copy = copy.deepcopy(rule)
    chk = rule_copy.get("check")
    if not isinstance(chk, dict):
        return rule_copy, False, None

    needs_comp = False
    for key in ("include", "exclude"):
        patterns = chk.get(key) or []
        if any("{{component_dirs}}" in p for p in patterns):
            needs_comp = True

    if not needs_comp:
        return rule_copy, False, None

    if not component_dirs:
        return rule_copy, True, "Skipped because design.component_dirs is empty in profile."

    new_excludes = []
    for pat in chk.get("exclude") or []:
        if "{{component_dirs}}" in pat:
            for cd in component_dirs:
                norm_cd = cd.replace("\\", "/").strip().rstrip("/")
                new_excludes.append(pat.replace("{{component_dirs}}", norm_cd))
        else:
            new_excludes.append(pat)
    chk["exclude"] = new_excludes

    new_includes = []
    for pat in chk.get("include") or []:
        if "{{component_dirs}}" in pat:
            for cd in component_dirs:
                norm_cd = cd.replace("\\", "/").strip().rstrip("/")
                new_includes.append(pat.replace("{{component_dirs}}", norm_cd))
        else:
            new_includes.append(pat)
    chk["include"] = new_includes

    return rule_copy, False, None


def cmd_list(args):
    packs = load_all_packs(get_packs_dir())
    if not packs:
        print("No rule packs found.")
        return
    print(f"Available rule packs ({len(packs)}):")
    for pid in sorted(packs):
        p = packs[pid]
        rules_cnt = len(p.get("rules", []))
        vc_cnt = len(p.get("verify_checks", []))
        print(f"  - {p['id']} (v{p.get('version', 1)}): {p.get('title', '')} ({rules_cnt} rules, {vc_cnt} checks)")


def cmd_show(args):
    p = load_pack(args.pack_id, get_packs_dir())
    print(f"Pack:    {p['id']} (v{p.get('version', 1)})")
    print(f"Title:   {p.get('title', '')}")
    if "applies_when" in p:
        aw = p["applies_when"]
        plats = ", ".join(aw.get("platforms", []))
        hints = ", ".join(aw.get("hints", []))
        print(f"Applies: platforms=[{plats}] hints=[{hints}]")
    print(f"Summary:\n{p.get('summary', '').strip()}\n")
    rules = p.get("rules", [])
    print(f"Rules ({len(rules)}):")
    for r in rules:
        chk_info = f" [{r['check']['type']}]" if "check" in r and isinstance(r["check"], dict) else " [manual]"
        print(f"  - {r['id']} ({r.get('area', '')}){chk_info}: {r.get('text', '')}")
    vc = p.get("verify_checks", [])
    if vc:
        print(f"\nVerify checks ({len(vc)}):")
        for c in vc:
            print(f"  - {c}")
    if "notes" in p:
        print(f"\nNotes: {p['notes']}")


def plan_pack_changes(pack: dict, prof: dict) -> dict:
    component_dirs = (prof.get("design") or {}).get("component_dirs", [])
    existing_rules = {r["id"]: r for r in prof.get("rules", []) if isinstance(r, dict) and "id" in r}
    dropped_rules = set(prof.get("dropped_pack_rules", []) or [])

    to_add = []
    conflicts = []
    skipped = []
    already_installed = []

    for r in pack.get("rules", []):
        rid = r["id"]
        if rid in dropped_rules:
            skipped.append((rid, "Rule is listed in dropped_pack_rules"))
            continue

        expanded_rule, is_skipped, skip_reason = expand_rule_variables(r, component_dirs)
        if is_skipped:
            skipped.append((rid, skip_reason))
            continue

        if rid in existing_rules:
            curr = existing_rules[rid]
            if curr.get("text") == expanded_rule.get("text"):
                already_installed.append(rid)
            else:
                conflicts.append({
                    "id": rid,
                    "existing_text": curr.get("text"),
                    "pack_text": expanded_rule.get("text")
                })
        else:
            to_add.append(expanded_rule)

    return {
        "to_add": to_add,
        "conflicts": conflicts,
        "skipped": skipped,
        "already_installed": already_installed
    }


def cmd_plan(args):
    packs_dir = get_packs_dir(getattr(args, "packs_dir", None))
    p = load_pack(args.pack_id, packs_dir)
    root = Path(getattr(args, "root", ".")).resolve()
    if Path(args.profile).is_absolute():
        prof_path = Path(args.profile).resolve()
    else:
        prof_path = (root / args.profile).resolve()
    if not prof_path.is_file():
        sys.exit(f"Profile not found: {prof_path}")
    prof = yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {}

    plan = plan_pack_changes(p, prof)
    print(f"Plan for pack '{p['id']}' (v{p.get('version', 1)}):")
    print(f"  Rules to add:       {len(plan['to_add'])}")
    for r in plan["to_add"]:
        enf = r.get("enforced_by", "manual")
        print(f"    + {r['id']} ({r.get('area', '')}) [{enf}]: {r.get('text', '')}")

    if plan["conflicts"]:
        print(f"\n  Conflicts ({len(plan['conflicts'])}):")
        for c in plan["conflicts"]:
            print(f"    ! {c['id']}: text differs from profile rule. Will NOT overwrite.")

    if plan["skipped"]:
        print(f"\n  Skipped ({len(plan['skipped'])}):")
        for s_id, s_reason in plan["skipped"]:
            print(f"    - {s_id}: {s_reason}")

    if plan["already_installed"]:
        print(f"\n  Already installed:  {len(plan['already_installed'])}")

    files = list_repo_files(root)
    violations_found = 0
    for r in plan["to_add"]:
        violations = probe_rule_violations(r, root, files)
        if violations:
            violations_found += len(violations)
            print(f"\n  Probe violation for rule '{r['id']}':")
            for v in violations[:5]:
                print(f"    {v['file']}:{v['line']}: {v['match']}")
            if len(violations) > 5:
                print(f"    ... and {len(violations) - 5} more")

    if violations_found > 0:
        print(f"\n  Total probe violations detected: {violations_found}")


def cmd_apply(args):
    packs_dir = get_packs_dir(getattr(args, "packs_dir", None))
    p = load_pack(args.pack_id, packs_dir)
    root = Path(getattr(args, "root", ".")).resolve()
    if Path(args.profile).is_absolute():
        prof_path = Path(args.profile).resolve()
    else:
        prof_path = (root / args.profile).resolve()
    if not prof_path.is_file():
        sys.exit(f"Profile not found: {prof_path}")
    prof = yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {}

    files = list_repo_files(root)

    except_ids = set()
    if args.except_rules:
        for x in args.except_rules.split(","):
            if x.strip():
                except_ids.add(x.strip())

    cli_exceptions = {}
    if args.exception:
        for item in args.exception:
            parts = item.split(":", 2)
            if len(parts) == 3:
                r_id, r_path, r_reason = parts[0].strip(), parts[1].strip(), parts[2].strip()
                if r_id not in cli_exceptions:
                    cli_exceptions[r_id] = []
                cli_exceptions[r_id].append({"path": r_path, "reason": r_reason})

    plan = plan_pack_changes(p, prof)
    rules_to_apply = []

    if plan["conflicts"]:
        print(f"Conflicts ({len(plan['conflicts'])}):")
        for c in plan["conflicts"]:
            print(f"  ! {c['id']}: text differs from profile rule. Preserving existing rule and not overwriting.")

    if plan["skipped"]:
        print(f"Skipped ({len(plan['skipped'])}):")
        for s_id, s_reason in plan["skipped"]:
            print(f"  - {s_id}: {s_reason}")

    for r in plan["to_add"]:
        rid = r["id"]
        if rid in except_ids:
            if "dropped_pack_rules" not in prof:
                prof["dropped_pack_rules"] = []
            if rid not in prof["dropped_pack_rules"]:
                prof["dropped_pack_rules"].append(rid)
            print(f"Skipping rule '{rid}' per --except and adding to dropped_pack_rules.")
            continue

        if rid in cli_exceptions:
            if "exceptions" not in r:
                r["exceptions"] = []
            r["exceptions"].extend(cli_exceptions[rid])

        violations = probe_rule_violations(r, root, files)
        if violations:
            print(f"Rule '{rid}' has {len(violations)} existing violation(s):")
            for v in violations[:5]:
                print(f"  {v['file']}:{v['line']}: {v['match']}")
            if len(violations) > 5:
                print(f"  ... and {len(violations) - 5} more")

            if not args.yes:
                sys.exit(f"Existing violations found for '{rid}'. Provide exceptions or fix code first.")
            else:
                if "exceptions" not in r:
                    r["exceptions"] = []
                for v in violations:
                    r["exceptions"].append({
                        "path": v["file"],
                        "reason": f"Pre-existing violation recorded on {p['id']} pack apply"
                    })
                print(f"Recorded {len(violations)} exception(s) for rule '{rid}'.")

        r["pack"] = f"{p['id']}@{p.get('version', 1)}"
        rules_to_apply.append(r)

    if not rules_to_apply and not plan["conflicts"] and not except_ids:
        print(f"Pack '{p['id']}' has no changes to apply.")
        return

    if not args.yes:
        print(f"Ready to apply {len(rules_to_apply)} rule(s) from '{p['id']}'. Pass --yes to write.")
        return

    if "rules" not in prof or not isinstance(prof["rules"], list):
        prof["rules"] = []
    prof["rules"].extend(rules_to_apply)

    vc = p.get("verify_checks") or []
    if vc:
        if "quality_gates" not in prof or not isinstance(prof["quality_gates"], list):
            prof["quality_gates"] = []
        for check_item in vc:
            if check_item not in prof["quality_gates"]:
                prof["quality_gates"].append(check_item)

    if "rule_packs" not in prof or not isinstance(prof["rule_packs"], list):
        prof["rule_packs"] = []

    existing_entry = next((entry for entry in prof["rule_packs"] if isinstance(entry, dict) and entry.get("id") == p["id"]), None)
    if existing_entry:
        existing_entry["version"] = p.get("version", 1)
    else:
        prof["rule_packs"].append({"id": p["id"], "version": p.get("version", 1)})

    prof_path.write_text(yaml.dump(prof, sort_keys=False), encoding="utf-8")
    print(f"Successfully applied {len(rules_to_apply)} rule(s) from pack '{p['id']}' to {prof_path}.")


def cmd_diff(args):
    packs_dir = get_packs_dir(getattr(args, "packs_dir", None))
    p = load_pack(args.pack_id, packs_dir)
    root = Path(getattr(args, "root", ".")).resolve()
    if Path(args.profile).is_absolute():
        prof_path = Path(args.profile).resolve()
    else:
        prof_path = (root / args.profile).resolve()
    if not prof_path.is_file():
        sys.exit(f"Profile not found: {prof_path}")
    prof = yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {}

    rule_packs = prof.get("rule_packs", []) or []
    installed_ver = None
    for entry in rule_packs:
        if isinstance(entry, dict) and entry.get("id") == p["id"]:
            installed_ver = entry.get("version")
            break

    if installed_ver is None:
        print(f"Pack '{p['id']}' is not recorded as installed in {args.profile}.")
        return

    print(f"Pack: {p['id']}")
    print(f"Installed version: v{installed_ver}")
    print(f"Packaged version:  v{p.get('version', 1)}")

    installed_rules = {
        r["id"]: r for r in prof.get("rules", [])
        if isinstance(r, dict) and r.get("pack", "").startswith(f"{p['id']}@")
    }
    packaged_rules = {r["id"]: r for r in p.get("rules", [])}

    added = [rid for rid in packaged_rules if rid not in installed_rules]
    removed = [rid for rid in installed_rules if rid not in packaged_rules]
    changed = []
    for rid in packaged_rules:
        if rid in installed_rules and packaged_rules[rid].get("text") != installed_rules[rid].get("text"):
            changed.append(rid)

    print(f"  Added rules in package:   {added if added else 'none'}")
    print(f"  Removed rules in package: {removed if removed else 'none'}")
    print(f"  Modified rule text:       {changed if changed else 'none'}")


def lint_pack_file(f: Path, all_seen_ids: dict, errors: list):
    try:
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    except Exception as e:
        errors.append(f"{f.name}: Invalid YAML syntax: {e}")
        return

    if not isinstance(data, dict):
        errors.append(f"{f.name}: Must be a YAML mapping")
        return

    pid = data.get("id")
    if not pid or pid != f.stem:
        errors.append(f"{f.name}: id '{pid}' must match file stem '{f.stem}'")

    ver = data.get("version")
    if ver is None or not isinstance(ver, int) or ver < 1:
        errors.append(f"{f.name}: version must be an integer >= 1")

    title = data.get("title")
    if not title or not isinstance(title, str):
        errors.append(f"{f.name}: title is required")

    summary = data.get("summary")
    if not summary or not isinstance(summary, str):
        errors.append(f"{f.name}: summary is required")
    else:
        summary_lines = [ln for ln in summary.strip().splitlines() if ln.strip()]
        if len(summary_lines) > 2:
            errors.append(f"{f.name}: summary must be 2 lines or fewer (got {len(summary_lines)})")

    rules = data.get("rules")
    if rules is None or not isinstance(rules, list):
        errors.append(f"{f.name}: rules must be a list")
        rules = []

    if len(rules) > 12:
        errors.append(f"{f.name}: rules count {len(rules)} exceeds limit of 12")

    for idx, r in enumerate(rules):
        if not isinstance(r, dict):
            errors.append(f"{f.name}: rules[{idx}] must be a mapping")
            continue
        rid = r.get("id")
        if not rid or not isinstance(rid, str):
            errors.append(f"{f.name}: rules[{idx}].id is required")
        else:
            if rid in all_seen_ids:
                errors.append(f"{f.name}: duplicate rule id '{rid}' across packs (already in {all_seen_ids[rid]})")
            else:
                all_seen_ids[rid] = f.name

        area = r.get("area")
        if area not in VALID_AREAS:
            errors.append(f"{f.name}: rule '{rid}' area '{area}' is not a valid area")

        text = r.get("text", "")
        if not text or not isinstance(text, str):
            errors.append(f"{f.name}: rule '{rid}' text is required")
        else:
            if len(text) > 160:
                errors.append(f"{f.name}: rule '{rid}' text length {len(text)} exceeds limit of 160 characters")
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
            if len(sentences) > 1:
                errors.append(f"{f.name}: rule '{rid}' text must be exactly 1 sentence (found {len(sentences)})")
            if "\u2014" in text or "\u2013" in text:
                errors.append(f"{f.name}: rule '{rid}' text contains em or en dashes")

        enf = r.get("enforced_by")
        if enf not in ("manual", "test", "lint"):
            errors.append(f"{f.name}: rule '{rid}' enforced_by must be manual, test, or lint")

        chk = r.get("check")
        if chk is not None:
            if not isinstance(chk, dict):
                errors.append(f"{f.name}: rule '{rid}' check must be a mapping")
            else:
                ctype = chk.get("type")
                if ctype not in ("forbid", "forbid_file", "require_file", "root_only", "no_dual_homed_skills"):
                    errors.append(f"{f.name}: rule '{rid}' check type '{ctype}' is invalid")
                hint = chk.get("hint")
                if not hint or not isinstance(hint, str) or not hint.strip():
                    errors.append(f"{f.name}: rule '{rid}' check must include a non-empty hint")
                exs = chk.get("examples")
                if not isinstance(exs, dict) or "bad" not in exs or "good" not in exs:
                    errors.append(f"{f.name}: rule '{rid}' check must include examples with 'bad' and 'good' lists")
                else:
                    if not isinstance(exs["bad"], list) or len(exs["bad"]) == 0:
                        errors.append(f"{f.name}: rule '{rid}' check.examples.bad must have at least 1 example")
                    if not isinstance(exs["good"], list) or len(exs["good"]) == 0:
                        errors.append(f"{f.name}: rule '{rid}' check.examples.good must have at least 1 example")

                    if ctype == "forbid":
                        pat = chk.get("pattern", "")
                        try:
                            rx = re.compile(pat)
                            for b in (exs.get("bad") or []):
                                if not rx.search(b):
                                    errors.append(f"{f.name}: rule '{rid}' selftest bad example did not match: {b}")
                            for g in (exs.get("good") or []):
                                if rx.search(g):
                                    errors.append(f"{f.name}: rule '{rid}' selftest good example unexpectedly matched: {g}")
                        except re.error as e:
                            errors.append(f"{f.name}: rule '{rid}' regex pattern '{pat}' failed to compile: {e}")
                    elif ctype == "forbid_file":
                        inc = chk.get("include") or []
                        exc = chk.get("exclude") or []
                        for b in (exs.get("bad") or []):
                            if not matching_files([b], inc, exc):
                                errors.append(f"{f.name}: rule '{rid}' selftest bad file example was not flagged: {b}")
                        for g in (exs.get("good") or []):
                            if matching_files([g], inc, exc):
                                errors.append(f"{f.name}: rule '{rid}' selftest good file example was flagged: {g}")
        elif enf == "test":
            errors.append(f"{f.name}: rule '{rid}' claims enforced_by test but has no check block")

    vc = data.get("verify_checks")
    if vc is not None:
        if not isinstance(vc, list):
            errors.append(f"{f.name}: verify_checks must be a list of sentences")
        else:
            for vidx, vline in enumerate(vc):
                if not isinstance(vline, str) or not vline.strip():
                    errors.append(f"{f.name}: verify_checks[{vidx}] must be a non-empty string")
                elif "\u2014" in vline or "\u2013" in vline:
                    errors.append(f"{f.name}: verify_checks[{vidx}] contains em or en dashes")


def lint_packs(packs_dir: Path = None) -> list:
    if packs_dir is None:
        packs_dir = get_packs_dir()
    packs_dir = Path(packs_dir).resolve()
    if not packs_dir.is_dir():
        return [f"Rule packs directory not found: {packs_dir}"]

    files = sorted(packs_dir.glob("*.yaml"))
    if not files:
        return [f"No rule pack files found in {packs_dir}"]

    errors = []
    seen_ids = {}
    for f in files:
        lint_pack_file(f, seen_ids, errors)
    return errors


def cmd_lint(args):
    packs_dir = get_packs_dir(getattr(args, "dir", None) or getattr(args, "packs_dir", None))
    errors = lint_packs(packs_dir)

    if errors:
        print(f"Rule pack lint failed with {len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    print(f"OK: All {len(list(packs_dir.glob('*.yaml')))} rule packs passed lint checks with 0 errors.")


def main():
    ap = argparse.ArgumentParser(description="Build Forge Rule Pack CLI")
    sp = ap.add_subparsers(dest="command", required=True)

    sp.add_parser("list", help="List available rule packs")

    p_show = sp.add_subparsers().add_parser("show", help="Show rule pack details") if False else sp.add_parser("show", help="Show rule pack details")
    p_show.add_argument("pack_id", help="Rule pack id")
    p_show.add_argument("--packs-dir", default=None, help="Custom rule packs directory")

    p_plan = sp.add_parser("plan", help="Plan changes against project profile")
    p_plan.add_argument("pack_id", help="Rule pack id")
    p_plan.add_argument("--profile", default=".agents/project-profile.yaml", help="Profile path")
    p_plan.add_argument("--root", default=".", help="Repository root path")
    p_plan.add_argument("--packs-dir", default=None, help="Custom rule packs directory")

    p_apply = sp.add_parser("apply", help="Apply pack rules to project profile")
    p_apply.add_argument("pack_id", help="Rule pack id")
    p_apply.add_argument("--profile", default=".agents/project-profile.yaml", help="Profile path")
    p_apply.add_argument("--root", default=".", help="Repository root path")
    p_apply.add_argument("--packs-dir", default=None, help="Custom rule packs directory")
    p_apply.add_argument("--except", dest="except_rules", default=None, help="Comma-separated rule ids to omit")
    p_apply.add_argument("--exception", action="append", help="rule:path:reason exception mapping")
    p_apply.add_argument("--yes", action="store_true", help="Confirm writing to profile without interactive prompt")

    p_diff = sp.add_parser("diff", help="Diff installed pack against packaged version")
    p_diff.add_argument("pack_id", help="Rule pack id")
    p_diff.add_argument("--profile", default=".agents/project-profile.yaml", help="Profile path")
    p_diff.add_argument("--root", default=".", help="Repository root path")
    p_diff.add_argument("--packs-dir", default=None, help="Custom rule packs directory")

    p_lint = sp.add_parser("lint", help="Lint all rule pack files")
    p_lint.add_argument("--dir", "--packs-dir", dest="dir", default=None, help="Custom rule packs directory")

    args = ap.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "plan":
        cmd_plan(args)
    elif args.command == "apply":
        cmd_apply(args)
    elif args.command == "diff":
        cmd_diff(args)
    elif args.command == "lint":
        cmd_lint(args)


if __name__ == "__main__":
    main()
