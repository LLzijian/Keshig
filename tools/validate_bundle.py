#!/usr/bin/env python3
"""Validate manifest, Skill metadata, privacy boundaries, links and tests."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from privacy_check import audit

ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / "skills"
TEXT_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".py", ".ps1", ".js", ".cjs", ".sql", ".txt"}
REPOSITORY_BLOCKED = {
    "private Windows absolute path": re.compile(r"\b[A-Za-z]:\\(?:[^\\/:*?\"<>|\r\n]+\\)+"),
    "private macOS home": re.compile(r"/Users/[^/\s]+/"),
    "private Linux home": re.compile(r"/home/[^/\s]+/"),
    "possible OpenAI secret": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    "possible bearer secret": re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}", re.IGNORECASE),
    "possible JWT or publishable key": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    "cloud runtime domain": re.compile(r"(?:tcb-api|tcloudbase)\.[A-Za-z0-9.-]+", re.IGNORECASE),
}
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---", re.S)


class ValidationFailure(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ValidationFailure(message)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        fail(f"Not UTF-8: {path}: {exc}")
    raise AssertionError("unreachable")


def run(command: list[str]) -> str:
    result = subprocess.run(command, cwd=ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True)
    if result.returncode:
        raise ValidationFailure("Command failed:\n" + " ".join(command) + "\n" + result.stdout + result.stderr)
    return (result.stdout or "") + (result.stderr or "")


def validate_manifest() -> tuple[str, ...]:
    manifest = json.loads(read_text(ROOT / "keshig.manifest.json"))
    names = tuple(item["name"] for item in manifest.get("skills", []))
    actual = tuple(sorted(path.name for path in SKILLS_ROOT.iterdir() if path.is_dir() and not path.name.startswith(".")))
    if tuple(sorted(names)) != actual:
        fail(f"Manifest Skill list mismatch: manifest={tuple(sorted(names))} actual={actual}")
    for item in manifest.get("skills", []):
        if not (ROOT / item["path"] / "SKILL.md").is_file():
            fail(f"Manifest path missing SKILL.md: {item['path']}")
    return names


def validate_skill(name: str) -> None:
    skill = SKILLS_ROOT / name
    text = read_text(skill / "SKILL.md")
    match = FRONT_MATTER.match(text)
    if not match:
        fail(f"SKILL.md missing front matter: {name}")
    declared = re.search(r"^name:\s*(\S+)", match.group(1), re.M)
    if not declared or declared.group(1) != name:
        fail(f"SKILL.md name does not match directory: {name}")
    if "description:" not in match.group(1):
        fail(f"SKILL.md missing description: {name}")
    for label, pattern in REPOSITORY_BLOCKED.items():
        if pattern.search(text):
            fail(f"{label} found in Skill: {name}")


def validate_repository_hygiene() -> None:
    if (ROOT / ".git").exists():
        for mode in ("worktree", "history"):
            errors, _ = audit(ROOT, mode)
            if errors:
                fail("Publication privacy check failed:\n" + "\n".join(errors))
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if any(part in {".git", "validation-output", "__pycache__", "node_modules", "test-results"} for part in rel.parts):
            continue
        if path.resolve() == Path(__file__).resolve() or not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = read_text(path)
        for label, pattern in REPOSITORY_BLOCKED.items():
            if pattern.search(text):
                fail(f"{label} found in repository file: {rel}")


def validate_links() -> None:
    md_files = [
        ROOT / "README.md",
        ROOT / "AGENTS.md",
        ROOT / "SYSTEM-FLOW.md",
        *sorted((ROOT / "docs").glob("*.md")),
        *sorted((ROOT / "knowledge").glob("*.md")),
        *sorted(SKILLS_ROOT.glob("*/SKILL.md")),
        *sorted(SKILLS_ROOT.glob("*/references/**/*.md")),
    ]
    for path in md_files:
        if not path.is_file():
            continue
        for target in LINK_RE.findall(read_text(path)):
            target = target.strip().strip("<>").split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (path.parent / target).resolve().exists():
                fail(f"Broken local link in {path.relative_to(ROOT)}: {target}")


def validate_beginner_guide() -> None:
    guide = ROOT / "docs" / "beginner-guide.md"
    if not guide.is_file():
        fail("Missing beginner setup guide: docs/beginner-guide.md")
    text = read_text(guide)
    for required in ("开始建立我的健身系统", "安全边界", "迁移到新电脑"):
        if required not in text:
            fail(f"Beginner guide is missing required instruction: {required}")


def validate_install() -> None:
    with tempfile.TemporaryDirectory(prefix="keshig-install-") as raw:
        target = Path(raw) / "agent"
        output = run([sys.executable, str(ROOT / "tools" / "install.py"), "--target-root", str(target), "--all"])
        for required in ("KESHIG_FITNESS_INSTALL: PASS", "KESHIG_FITNESS_VERIFY: PASS", "KESHIG_FITNESS_AI_ONBOARDING:"):
            if required not in output:
                fail(f"Installer is missing required output: {required}")
        verify = run([sys.executable, str(ROOT / "tools" / "install.py"), "--target-root", str(target), "--all", "--verify"])
        if "KESHIG_FITNESS_VERIFY: PASS" not in verify:
            fail("Installed bundle did not pass the drift check")


def validate_tests() -> None:
    run([sys.executable, "-B", str(ROOT / "tools" / "sync_training_progression.py"), "--check"])
    checks = [
        "skills/douyin-question-distiller/scripts/test_distill_report.py",
        "tools/test_video_learning.py",
        "tools/test_learning_outputs.py",
        "tools/test_installer.py",
        "tools/test_product_safety.py",
        "tools/test_device.py",
        "skills/training-system/scripts/Test-TrainingSystemInspectReadOnly.py",
        "skills/training-system/scripts/Test-TrainingSystemPortability.py",
        "skills/training-expert-library/scripts/validate_expert_library.py",
        "skills/nutrition-system/scripts/test_nutrition_system.py",
        "tools/test_health_db.py",
    ]
    for relative in checks:
        run([sys.executable, "-B", str(ROOT / relative)])


def main() -> None:
    names = validate_manifest()
    for name in names:
        validate_skill(name)
    validate_beginner_guide()
    validate_links()
    validate_repository_hygiene()
    validate_tests()
    validate_install()
    print("OK: Keshig bundle passed the configured publication, portability and installation checks.")
    print(f"Validated Skills: {len(names)}")


if __name__ == "__main__":
    try:
        main()
    except ValidationFailure as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
