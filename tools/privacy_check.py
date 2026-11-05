#!/usr/bin/env python3
"""Check publication candidates locally, without printing their contents."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
from install import is_reparse_point

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIRS = {"skills", "knowledge", "device", "schema", "tools", "docs", "examples", "licenses", "third_party", ".github", ".githooks"}
PUBLIC_FILES = {".gitignore", ".gitattributes", "AGENTS.md", "README.md", "LICENSE", "NOTICE.md", "THIRD-PARTY-NOTICES.md", "SYSTEM-FLOW.md", "keshig.manifest.json"}
TEXT_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".py", ".ps1", ".sh", ".sql", ".txt", ".toml"}
PRIVATE_DIRS = {"系统", "个人训练系统", "健身知识库", "profiles", "plans", "reviews", "handoffs", "runtime", "data", "backups", ".fitness", ".venv", "node_modules", "__pycache__"}
PATTERNS = {
    "private machine path": re.compile(r"(?:\b[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/][^\s\"'<>]+|/(?:Users|home)/[A-Za-z0-9_. -]+/)", re.I),
    "secret token": re.compile(r"\bsk-" + r"[A-Za-z0-9_-]{16,}\b|Bearer\s+" + r"[A-Za-z0-9._-]{20,}", re.I),
    "JWT": re.compile(r"\beyJ" + r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    "private key": re.compile("-----BEGIN " + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "credential assignment": re.compile(r'''["']?(?:api_key|access_token|refresh_token|password)["']?\s*[:=]\s*["'](?!<|\$|example|your_|test_)[A-Za-z0-9_+/=.-]{12,}["']''', re.I),
}


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if result.returncode:
        raise ValueError("Git 检查失败；请在完整的 Keshig 仓库中运行")
    return result.stdout


def names(raw: bytes) -> list[str]:
    return [part.decode("utf-8") for part in raw.split(b"\0") if part]


def check_file(name: str, content: bytes) -> list[str]:
    path = PurePosixPath(name)
    errors = []
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        return ["invalid publication path"]
    if any(part.casefold() in PRIVATE_DIRS or part.casefold().endswith("-output") for part in path.parts):
        errors.append("personal or runtime directory")
    if name not in PUBLIC_FILES and (path.parts[0] not in PUBLIC_DIRS or
            path.suffix not in TEXT_SUFFIXES and path.name not in {"LICENSE", "pre-commit", "pre-push"}):
        errors.append("file is outside the publication allowlist")
    if path.name.startswith(".env") or any(term in path.name.lower() for term in ("credential", "secret")):
        if not path.name.endswith(".example.json"):
            errors.append("credential file")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return errors + ["non-text content"]
    for label, pattern in PATTERNS.items():
        if pattern.search(text):
            errors.append(label)
    return errors


def candidates(root: Path, mode: str, revisions=()):
    if mode == "staged":
        for entry in git(root, "ls-files", "--stage", "-z").split(b"\0"):
            if not entry:
                continue
            metadata, raw_name = entry.split(b"\t", 1)
            permissions, oid, stage = metadata.split()
            name = raw_name.decode("utf-8")
            yield name, git(root, "cat-file", "blob", oid.decode()) if permissions in (b"100644", b"100755") and stage == b"0" else b"\x00\xff"
    elif mode == "history":
        # Inspect every reachable commit, including files removed in later commits.
        seen = set()
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "--quiet", "HEAD"], capture_output=True)
        selected = [*revisions, *(["HEAD"] if head.returncode == 0 else [])]
        for commit in git(root, "rev-list", "--all", *selected).decode().splitlines():
            for entry in git(root, "ls-tree", "-r", "-z", commit).split(b"\0"):
                if not entry:
                    continue
                metadata, raw_name = entry.split(b"\t", 1)
                permissions, kind, oid = metadata.split()
                name = raw_name.decode("utf-8")
                key = (name, oid)
                if key in seen:
                    continue
                seen.add(key)
                if permissions not in (b"100644", b"100755") or kind != b"blob":
                    yield name, b"\x00\xff"
                else:
                    yield name, git(root, "cat-file", "blob", oid.decode())
    else:
        for name in names(git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")):
            path = root / name
            if not path.exists() and not path.is_symlink():
                continue
            parents = list(path.parents)[:len(path.relative_to(root).parts)]
            if any(is_reparse_point(p) for p in [path, *parents]) or not path.resolve().is_relative_to(root.resolve()):
                yield name, b"\x00\xff"
            elif path.is_file():
                yield name, path.read_bytes()


def audit(root: Path, mode: str, revisions=()) -> tuple[list[str], list[tuple[str, bytes]]]:
    errors, files = [], []
    for name, content in candidates(root, mode, revisions):
        issues = check_file(name, content)
        errors.extend(f"{name}: {issue}" for issue in issues)
        files.append((name, content))
    return errors, files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("staged", "worktree", "history"), default="worktree")
    parser.add_argument("--pre-push", action="store_true", help="Also check exact local revisions supplied by Git")
    args = parser.parse_args()
    try:
        revisions = []
        if args.pre_push:
            for line in sys.stdin:
                fields = line.split()
                if len(fields) != 4 or not re.fullmatch(r"[0-9a-f]{40,64}", fields[1]):
                    raise ValueError("无法识别待推送的本地版本")
                if set(fields[1]) != {"0"}:
                    revisions.append(fields[1])
        errors, files = audit(ROOT, args.mode, revisions)
    except (OSError, ValueError) as exc:
        print("privacy_check: FAIL " + str(exc))
        return 1
    print(json.dumps({"check": args.mode, "files_checked": len(files), "errors": errors}, ensure_ascii=False, indent=2))
    print("privacy_check: " + ("FAIL" if errors else "PASS"))
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
