"""Common utilities for blueprint analyzers."""
import hashlib
import os
import re
from pathlib import Path

IGNORE_DIRS = {
    ".git", ".svn", "node_modules", "dist", "build", "target", "vendor",
    "__pycache__", ".venv", "venv", ".agents", ".gemini", ".claude"
}

SECRET_FILE_PATTERNS = [
    re.compile(r"^\.env(?!\.example$)", re.IGNORECASE),
    re.compile(r".*\.pem$", re.IGNORECASE),
    re.compile(r".*\.key$", re.IGNORECASE),
    re.compile(r"^id_rsa", re.IGNORECASE),
    re.compile(r"^credentials\.json$", re.IGNORECASE),
]

SECRET_TEXT_PATTERNS = [
    re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----"),
    re.compile(r"(?:api[_-]?key|secret|password|access[_-]?token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]", re.IGNORECASE),
    re.compile(r"\b(?:sk|pk|ghp|gho)_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
]


def is_secret_file(filename: str) -> bool:
    """Return True if filename should be excluded as a secret file."""
    for pat in SECRET_FILE_PATTERNS:
        if pat.search(filename):
            return True
    return False


def scan_for_secrets(text: str) -> list:
    """Return matches if text contains patterns resembling secrets."""
    matches = []
    for pat in SECRET_TEXT_PATTERNS:
        found = pat.findall(text)
        if found:
            matches.extend(found)
    return matches


def find_files(root: Path, extensions: set, max_files: int = 1000) -> list:
    """Find all source files matching extensions while respecting ignore rules."""
    collected = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored directories
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        for fn in sorted(filenames):
            if is_secret_file(fn):
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext in extensions:
                full_path = Path(dirpath) / fn
                rel_path = full_path.relative_to(root).as_posix()
                collected.append(rel_path)
                if len(collected) >= max_files:
                    return sorted(collected)
    return sorted(collected)


def read_source_file(root: Path, rel_path: str) -> str:
    """Read file content with UTF-8 encoding and LF normalization."""
    p = root / rel_path
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        return content.replace("\r\n", "\n").replace("\r", "\n")
    except Exception:
        return ""


def hash_file_lf(root: Path, rel_path: str) -> str:
    """Compute deterministic SHA-256 hash of LF-normalized file."""
    content = read_source_file(root, rel_path)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
