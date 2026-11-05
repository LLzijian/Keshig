#!/usr/bin/env python3
"""Enable local privacy hooks; preserve an existing hook configuration."""
import subprocess
import sys
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    existing = subprocess.run(["git", "config", "--get", "core.hooksPath"], cwd=ROOT,
                              capture_output=True, text=True)
    if existing.returncode not in (0, 1):
        raise SystemExit("无法读取 Git 设置")
    if existing.stdout.strip() not in ("", ".githooks"):
        raise SystemExit("已有自定义 Git hooks；保留原设置，请手动串接 Keshig 隐私检查。")
    if not existing.stdout.strip():
        output = subprocess.run(["git", "rev-parse", "--git-path", "hooks"], cwd=ROOT,
                                check=True, capture_output=True, text=True).stdout.strip()
        hooks = Path(output) if Path(output).is_absolute() else ROOT / output
        if any(path.is_file() and not path.name.endswith(".sample") for path in hooks.glob("*")):
            raise SystemExit("已有 Git hooks；保留原文件，请手动串接 Keshig 隐私检查。")
    for name in ("pre-commit", "pre-push"):
        path = ROOT / ".githooks" / name
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    for key, value in (("keshig.python", sys.executable), ("core.hooksPath", ".githooks")):
        result = subprocess.run(["git", "config", "--local", key, value], cwd=ROOT)
        if result.returncode:
            raise SystemExit(result.returncode)
    print("开发保护已启用：提交前检查暂存区，推送前检查本地 Git 历史。")


if __name__ == "__main__":
    main()
