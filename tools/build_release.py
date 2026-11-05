#!/usr/bin/env python3
"""Build an allowlisted source bundle after local privacy and history checks."""
import argparse
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from privacy_check import ROOT, audit


def build(root: Path, destination: Path) -> int:
    errors, files = audit(root, "worktree")
    history_errors, _ = audit(root, "history")
    if errors or history_errors:
        raise ValueError("发布检查失败：\n" + "\n".join(errors + history_errors))
    if destination.exists():
        raise ValueError("目标已存在，拒绝覆盖")
    destination.parent.mkdir(parents=True, exist_ok=True)
    version = json.loads((root / "keshig.manifest.json").read_text(encoding="utf-8"))["version"]
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files:
            archive.writestr(f"keshig-{version}/{name}", content)
    return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "release-output" / "keshig.zip")
    args = parser.parse_args()
    try:
        count = build(ROOT, args.output)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(f"release: PASS files={count} output={args.output}")


if __name__ == "__main__":
    main()
