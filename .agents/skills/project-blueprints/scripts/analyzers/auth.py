"""Auth analyzer: libraries, providers, guards, and logout cleanup paths."""
import json
import re
from pathlib import Path
from .common import find_files, read_source_file

AUTH_LIBS = [
    "@auth/core", "next-auth", "@supabase/supabase-js", "@supabase/auth-helpers-nextjs",
    "firebase", "@clerk/nextjs", "@clerk/clerk-react", "lucia", "passport", "auth0"
]


def detect(root: Path, profile: dict) -> bool:
    """Return True if auth libraries or auth files exist."""
    pkg_file = root / "package.json"
    if pkg_file.is_file():
        try:
            data = json.loads(pkg_file.read_text(encoding="utf-8"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            if any(lib in deps for lib in AUTH_LIBS):
                return True
        except Exception:
            pass
    files = find_files(root, {".ts", ".tsx", ".js", ".jsx"}, max_files=10)
    for f in files:
        if "auth" in f.lower() or "login" in f.lower() or "session" in f.lower():
            return True
    return False


def extract(root: Path, profile: dict) -> dict:
    """Extract auth facts, guards, logout mechanisms, and rule candidates."""
    facts = []
    candidates = []
    sources = set()

    detected_libs = []
    providers = []
    guards = []
    logout_paths = []

    # Check package.json dependencies
    pkg_file = root / "package.json"
    if pkg_file.is_file():
        try:
            data = json.loads(pkg_file.read_text(encoding="utf-8"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            for lib in AUTH_LIBS:
                if lib in deps:
                    detected_libs.append(lib)
                    facts.append({
                        "name": f"Auth Library: {lib}",
                        "evidence": "package.json:1",
                        "confidence": "high",
                        "details": [f"Version: {deps[lib]}"]
                    })
                    sources.add("package.json")
        except Exception:
            pass

    code_files = find_files(root, {".ts", ".tsx", ".js", ".jsx"})
    for rel_path in code_files:
        content = read_source_file(root, rel_path)
        if not content:
            continue
        lines = content.split("\n")
        has_auth = False

        # Auth context or guard by filename
        b_name = Path(rel_path).stem.lower()
        if "authcontext" in b_name or "authprovider" in b_name:
            facts.append({
                "name": f"Auth Context: {Path(rel_path).stem}",
                "evidence": f"{rel_path}:1",
                "confidence": "high",
                "details": [f"File: {rel_path}"]
            })
            has_auth = True
        elif "guard" in b_name or "middleware" in b_name:
            guards.append({
                "name": f"Route Guard: {Path(rel_path).stem}",
                "evidence": f"{rel_path}:1"
            })
            has_auth = True

        for idx, line in enumerate(lines, start=1):
            s_line = line.strip()

            # Providers: OAuth, magic link, password
            if re.search(r"\b(?:signInWithOAuth|signInWithPassword|signInWithOtp|signInWithPopup|signInWithRedirect)\b", s_line):
                m_prov = re.search(r"\b(signInWith[A-Za-z0-9]+)\b", s_line)
                p_name = m_prov.group(1) if m_prov else "Provider Call"
                providers.append({
                    "name": f"Provider Call: {p_name}",
                    "evidence": f"{rel_path}:{idx}"
                })
                has_auth = True

            # Logout mechanisms and storage cleanup
            if re.search(r"\b(?:signOut|logout|logOut)\b", s_line):
                # Check surrounding lines for clear storage
                window = lines[max(0, idx - 1): min(len(lines), idx + 8)]
                cleans_storage = any("localStorage.clear()" in w or "sessionStorage.clear()" in w or "removeItem" in w for w in window)
                logout_paths.append({
                    "name": "Logout handler",
                    "evidence": f"{rel_path}:{idx}",
                    "clears_storage": cleans_storage
                })
                has_auth = True

            # Validation constants -> candidates only
            if re.search(r"\b(?:min_age|max_age|password_min|min_password_length)\b", s_line, re.IGNORECASE):
                candidates.append({
                    "id": f"auth-validation-{len(candidates) + 1}",
                    "area": "auth",
                    "rule": f"Enforce credential boundary: {s_line[:60]}",
                    "evidence": f"{rel_path}:{idx}"
                })
                has_auth = True
            elif re.search(r"const\s+[A-Za-z0-9_]*(?:PASSWORD|REGEX|EMAIL)[A-Za-z0-9_]*\s*=\s*/[^/]+/", s_line):
                candidates.append({
                    "id": f"auth-regex-{len(candidates) + 1}",
                    "area": "auth",
                    "rule": f"Validation regex constraint: {s_line[:60]}",
                    "evidence": f"{rel_path}:{idx}"
                })
                has_auth = True

        if has_auth:
            sources.add(rel_path)

    # Compile facts
    for p in sorted(providers, key=lambda x: (x["name"], x["evidence"])):
        facts.append({
            "name": p["name"],
            "evidence": p["evidence"],
            "confidence": "high",
            "details": ["Authentication provider invocation"]
        })

    for g in sorted(guards, key=lambda x: (x["name"], x["evidence"])):
        facts.append({
            "name": g["name"],
            "evidence": g["evidence"],
            "confidence": "high",
            "details": ["Route access protection"]
        })

    for lp in sorted(logout_paths, key=lambda x: (x["name"], x["evidence"])):
        detail_txt = "Clears client storage or session" if lp["clears_storage"] else "Signs out user session"
        facts.append({
            "name": f"Logout Action (cleans storage: {lp['clears_storage']})",
            "evidence": lp["evidence"],
            "confidence": "high",
            "details": [detail_txt]
        })

    return {
        "facts": sorted(facts, key=lambda x: (x["name"], x["evidence"])),
        "detected_libs": detected_libs,
        "providers": providers,
        "guards": guards,
        "logout_paths": logout_paths,
        "candidates": candidates,
        "sources": sorted(sources),
        "unsupported": []
    }


def render(data: dict) -> str:
    """Render auth facts to markdown format."""
    lines = ["# Auth Blueprint\n"]
    lines.append("Extracted auth libraries, authentication providers, guards, and logout cleanup paths.\n")

    lines.append("## Auth architecture and libraries\n")
    if not data["detected_libs"]:
        lines.append("- No explicit authentication libraries found in dependencies.\n")
    else:
        for lib in sorted(data["detected_libs"]):
            lines.append(f"- Library: `{lib}`")

    lines.append("\n## Providers and guards\n")
    if not data["facts"]:
        lines.append("- No authentication provider calls or route guards detected.\n")
    else:
        for f in data["facts"]:
            lines.append(f"- **{f['name']}** (`{f['evidence']}`)")

    return "\n".join(lines).strip() + "\n"
