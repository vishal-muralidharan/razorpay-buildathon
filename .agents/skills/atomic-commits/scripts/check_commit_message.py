#!/usr/bin/env python3
"""Check a commit message against the git rules in the project profile.

Usage: python check_commit_message.py --profile PATH "message"

Exit 0 when there are no errors. Exit 1 otherwise. Warnings are advice.
Supports formats built from <type>, <scope> and one subject placeholder, for
example "<type>(<scope>): <subject>", "<type>: <subject>" or
"<type>(<scope>): <present tense subject>".
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


def build_regex(fmt):
    """Turn a format like "<type>(<scope>): <present tense subject>" into a regex.

    <type> and <scope> are recognized by name. Any other placeholder is the
    subject (for example <subject> or <present tense subject>).
    """
    parts = re.split(r"(<[^>]+>)", fmt)
    out, seen_subject = [], False
    for part in parts:
        if part == "<type>":
            out.append(r"(?P<type>[A-Za-z]+)")
        elif part == "<scope>":
            out.append(r"(?P<scope>[\w./-]+)")
        elif part.startswith("<") and part.endswith(">"):
            if seen_subject:
                out.append(r".+")
            else:
                out.append(r"(?P<subject>.+)")
                seen_subject = True
        else:
            out.append(re.escape(part))
    return re.compile("^" + "".join(out) + "$")



DEFAULT_PROFILE = ".agents/project-profile.yaml"


def resolve_profile_arg(profile, root=None) -> str:
    """Return the profile path. Defaults to .agents/project-profile.yaml under --root or the current folder."""
    if profile:
        return profile
    candidate = Path(root or ".") / DEFAULT_PROFILE
    if not candidate.is_file():
        sys.exit(f"ERROR: no profile at {candidate}. Pass --profile <path>.")
    return str(candidate)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=None, help="Defaults to .agents/project-profile.yaml")
    ap.add_argument("message")
    a = ap.parse_args()
    a.profile = resolve_profile_arg(a.profile)

    prof = yaml.safe_load(Path(a.profile).read_text()) or {}
    git = prof.get("git") or {}
    fmt = git.get("commit_format") or "<type>(<scope>): <subject>"
    types = git.get("types") or []
    raw_scopes = git.get("scopes") or []
    scopes = []
    for s in raw_scopes:
        if isinstance(s, str):
            scopes.append(s)
        elif isinstance(s, dict) and s.get("name"):
            scopes.append(str(s["name"]))
    msg = a.message.rstrip("\n")

    errors, warnings = [], []

    if git.get("single_line", True) and "\n" in msg:
        errors.append("message must be a single line")
    first = msg.split("\n")[0]

    m = build_regex(fmt).match(first)
    if not m:
        errors.append(f"does not match the format {fmt}")
    else:
        d = m.groupdict()
        if types and d.get("type") not in types:
            errors.append(f"type '{d.get('type')}' is not allowed. Use one of: {', '.join(types)}")
        if "scope" in d and scopes and d.get("scope") not in scopes:
            errors.append(f"scope '{d.get('scope')}' is not in git.scopes. Use one of: {', '.join(scopes)}")
        subject = (d.get("subject") or "").strip()
        if not subject:
            errors.append("subject is empty")
        else:
            if subject.endswith("."):
                warnings.append("subject should not end with a period")
            word = subject.split()[0].lower()
            if word.endswith("ed") and len(word) > 4:
                warnings.append(f"'{word}' looks past tense. Use the present tense")
            if subject[0].isupper():
                warnings.append("subject should start in lowercase")
    if len(first) > 72:
        warnings.append(f"line is {len(first)} characters. Keep it under 72")

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    if not errors:
        print("OK")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
