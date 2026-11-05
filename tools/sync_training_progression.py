#!/usr/bin/env python3
"""Synchronize and verify the shared training progression protocol across Skills."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "knowledge" / "training-progression.json"
TARGETS = (
    ROOT / "skills" / "training-system" / "references" / "training-progression-protocol.md",
    ROOT / "skills" / "fitness-plan" / "references" / "training-progression-protocol.md",
    ROOT / "skills" / "strength-cycle-planner" / "references" / "training-progression-protocol.md",
    ROOT / "skills" / "strength-training-review" / "references" / "training-progression-protocol.md",
    ROOT / "skills" / "training-return" / "references" / "training-progression-protocol.md",
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_master() -> dict:
    data = json.loads(MASTER.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("text"), str):
        raise SystemExit(f"Invalid master progression file: {MASTER}")
    return data


def sync(write: bool = False, installed_root: Path | None = None) -> int:
    data = load_master()
    text = data["text"]
    if not text.endswith("\n"):
        text += "\n"
    expected_sha = sha256_text(text)

    if write and data.get("sha256") != expected_sha:
        data["sha256"] = expected_sha
        MASTER.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    problems: list[str] = []
    if data.get("sha256") != expected_sha:
        problems.append(f"Master sha256 mismatch: declared={data.get('sha256')} actual={expected_sha}")

    targets = list(TARGETS)
    if installed_root:
        for skill in (
            "training-system",
            "fitness-plan",
            "strength-cycle-planner",
            "strength-training-review",
            "training-return",
        ):
            candidate = installed_root / skill / "references" / "training-progression-protocol.md"
            if candidate.parent.is_dir():
                targets.append(candidate)

    for target in targets:
        if write:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        if not target.is_file():
            problems.append(f"Missing target: {target}")
            continue
        actual_text = target.read_text(encoding="utf-8")
        if sha256_text(actual_text) != expected_sha:
            problems.append(f"Out of sync: {target}")

    if problems:
        print("TRAINING_PROGRESSION_SYNC: FAIL", file=sys.stderr)
        for item in problems:
            print("- " + item, file=sys.stderr)
        return 1

    print(f"TRAINING_PROGRESSION_SYNC: PASS version={data.get('version')} sha256={expected_sha}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write master text and sha256 to all Skill replicas")
    parser.add_argument("--check", action="store_true", help="Verify master sha256 and all Skill replicas match")
    parser.add_argument("--installed-root", type=Path, help="Optional installed skills directory to sync/check")
    args = parser.parse_args()
    return sync(write=args.write, installed_root=args.installed_root)


if __name__ == "__main__":
    raise SystemExit(main())
