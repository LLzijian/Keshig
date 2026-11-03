#!/usr/bin/env python
"""VitalDock 只读适配器 —— 怯薛 device 层。

只做一件事：把上游设备桥（华为运动健康 → Intervals.icu）的 CLI 输出变成结构化 JSON。

    python vitaldock_client.py selftest
    python vitaldock_client.py check      --day 2026-11-02
    python vitaldock_client.py wellness   --day 2026-11-02 --history-days 28
    python vitaldock_client.py activities --day 2026-11-02 --history-days 28

约束（硬）：
- 只 subprocess 调上游 CLI，读 stdout；**不 import 上游源码**。
- **不写上游目录、不改上游文件**；`selftest` 会顺手查一次 `git status --porcelain`。
- 上游路径用 `VITALDOCK_HOME` 覆盖。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PY_CANDIDATES = (
    Path(".venv/Scripts/python.exe"),
    Path(".venv/bin/python"),
    Path("venv/Scripts/python.exe"),
)

# 同级目录下常见的上游检出目录名，按序探测；第一个存在的生效。
SIBLING_NAMES = ("vitaldock", "VitalDock", "BioDeviceData")


def default_home() -> Path:
    parent = Path(__file__).resolve().parents[2]
    for name in SIBLING_NAMES:
        candidate = parent / name
        if candidate.is_dir():
            return candidate
    return parent / SIBLING_NAMES[0]


def upstream_home() -> Path:
    return Path(os.environ.get("VITALDOCK_HOME") or default_home())


def upstream_python(home: Path) -> Path | None:
    for rel in PY_CANDIDATES:
        p = home / rel
        if p.is_file():
            return p
    return None


def run(home: Path, py: Path, args: list[str], timeout: float) -> tuple[int, str, str]:
    """调上游 CLI。绝不写上游目录。"""
    cmd = [str(py), "-m", "vitaldock", *args]
    try:
        proc = subprocess.run(
            cmd, cwd=str(home), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", json.dumps({"error": "timeout", "timeout_s": timeout})


def parse_payload(rc: int, out: str, err: str):
    """上游约定：退出码 0 成功（含「无记录」），1 失败且 stderr 是 JSON。"""
    text = (out or "").strip()
    if rc == 0:
        if not text:
            return {"ok": True, "records": []}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"ok": True, "raw": text[:4000]}
    payload = {"ok": False, "exit_code": rc}
    for chunk in (err or "", out or ""):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            payload.update(json.loads(chunk))
            break
        except json.JSONDecodeError:
            payload["stderr_tail"] = chunk[-1200:]
    return payload


def cmd_selftest(args) -> int:
    home = upstream_home()
    py = upstream_python(home)
    report = {
        "vitaldock_home": str(home),
        "home_exists": home.is_dir(),
        "python": str(py) if py else None,
        "python_exists": bool(py and py.is_file()),
        "module_help_ok": None,
        "upstream_worktree_clean": None,
    }
    if py:
        rc, out, err = run(home, py, ["--help"], args.timeout)
        report["module_help_ok"] = rc == 0
        if rc != 0:
            report["module_help_error"] = (err or out)[-600:]
        try:
            git = subprocess.run(["git", "status", "--porcelain"], cwd=str(home),
                                 capture_output=True, text=True, timeout=30)
            report["upstream_worktree_clean"] = git.returncode == 0 and not git.stdout.strip()
            if git.stdout.strip():
                report["upstream_dirty_entries"] = git.stdout.strip().splitlines()[:10]
        except Exception as exc:  # noqa: BLE001 - 自检不该因 git 缺失而失败
            report["upstream_worktree_clean"] = None
            report["git_error"] = str(exc)[:200]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if (report["home_exists"] and report["python_exists"] and report["module_help_ok"]) else 1


def _device_cmd(subcommand: str):
    def _run(args) -> int:
        home = upstream_home()
        py = upstream_python(home)
        if not py:
            print(json.dumps({"ok": False, "error": "credential_not_configured",
                              "detail": f"找不到上游 venv python：{home}"}, ensure_ascii=False, indent=2))
            return 2
        argv = [subcommand, "--day", args.day]
        if args.history_days is not None:
            argv += ["--history-days", str(args.history_days)]
        if subcommand == "recent-activities" and args.limit is not None:
            argv += ["--limit", str(args.limit)]
        rc, out, err = run(home, py, argv, args.timeout)
        payload = parse_payload(rc, out, err)
        payload.setdefault("upstream_command", " ".join(["vitaldock", *argv]))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") else 1
    return _run


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="VitalDock 只读适配器（不写上游）")
    ap.add_argument("--timeout", type=float, default=120.0, help="单次上游调用超时秒数")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("selftest", help="检查路径与上游 CLI 是否可用，不联网").set_defaults(
        func=cmd_selftest)

    for name, upstream in (("check", "check-connection"),
                           ("wellness", "wellness-context"),
                           ("activities", "recent-activities")):
        p = sub.add_parser(name, help=f"等价于上游 {upstream}")
        p.add_argument("--day", required=True, help="YYYY-MM-DD")
        p.add_argument("--history-days", type=int, default=None)
        if name == "activities":
            p.add_argument("--limit", type=int, default=None)
        p.set_defaults(func=_device_cmd(upstream))

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
