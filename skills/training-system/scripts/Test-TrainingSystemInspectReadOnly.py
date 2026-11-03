#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ensure compact inspection never migrates or writes a legacy configuration."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SYSTEM = SCRIPT_DIR / "training_system.py"


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True, env=env)
    if result.returncode != 0:
        raise AssertionError("命令失败:\n" + " ".join(command) + "\n" + result.stdout + result.stderr)
    return result


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="fitness-inspect-readonly-") as tmp:
        root = Path(tmp) / "system"
        run([sys.executable, str(SYSTEM), "bootstrap", "--target", str(root)])
        config_path = root / "系统" / "keshig-system.json"
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        config["project_root"] = str((Path(tmp) / "legacy-machine" / "personal-training-system").resolve())
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        before_config = config_path.read_bytes()
        before_files = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())

        result = run([sys.executable, str(SYSTEM), "inspect", "--root", str(root)])
        summary = json.loads(result.stdout)
        require(summary.get("kind") == "keshig_system_summary", "inspect 未返回紧凑摘要")
        require(config_path.read_bytes() == before_config, "inspect 改写了旧配置")
        after_files = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
        require(after_files == before_files, "inspect 创建了迁移备份或其他文件")


    print("training_system_INSPECT_READ_ONLY: PASS")


if __name__ == "__main__":
    main()
