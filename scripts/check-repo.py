#!/usr/bin/env python3
"""Check the publishable tree for local state, concrete home paths, and common secrets."""

import re
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
ROOT_FILES = {"README.md", "AGENTS.md", "POLICY.md", ".gitignore", ".gitattributes"}
ALLOWED_DIRS = {"docs", "templates", "scripts", "tests"}
LOCAL_NAMES = {"tools.json", "TOOLS.md", "inventory.json", "policy-source.json", ".env"}
PATTERNS = [
    ("concrete user-home path", re.compile(r"/(?:Users|home)/[A-Za-z0-9_.-]+/")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("API token", re.compile(r"\b(?:cs-sk-[0-9a-f-]{24,}|sk-[A-Za-z0-9_-]{28,})")),
]


def candidates(root):
    result = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"], capture_output=True)
    if result.returncode == 0:
        return sorted({Path(name.decode("utf-8")) for name in result.stdout.split(b"\0") if name})
    return sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file() and ".git" not in path.parts and "__pycache__" not in path.parts)


def check(root):
    errors = []
    files = candidates(root)
    for relative in files:
        path = root / relative
        if relative.parts[0] not in ALLOWED_DIRS and str(relative) not in ROOT_FILES:
            errors.append(str(relative) + ": unexpected publishable path")
        if len(relative.parts) == 1 and relative.name in LOCAL_NAMES:
            errors.append(str(relative) + ": machine state must remain local")
        if path.is_symlink():
            errors.append(str(relative) + ": symlink is not allowed in this portable repository")
            continue
        if not path.is_file():
            errors.append(str(relative) + ": missing file")
            continue
        if path.stat().st_size > 256 * 1024:
            errors.append(str(relative) + ": unexpected large file")
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            errors.append(str(relative) + ": unexpected binary or unreadable file")
            continue
        for label, pattern in PATTERNS:
            if pattern.search(content):
                errors.append(str(relative) + ": " + label)
        if path.suffix == ".md":
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", content):
                if target.startswith(("https://", "http://", "#", "mailto:")):
                    continue
                local = target.split("#", 1)[0]
                if local and not (path.parent / local).is_file():
                    errors.append(str(relative) + ": broken document link " + local)
    return files, errors


if __name__ == "__main__":
    files, errors = check(ROOT)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        raise SystemExit(1)
    print("Publishable tree checks passed: " + str(len(files)) + " files.")
