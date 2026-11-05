#!/usr/bin/env python3
"""Prepare a private VitalDock runtime and read its public JSON CLI."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import venv
from pathlib import Path

# run_path is used by the compatible source-checkout entry.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import training_system as system

LOCK = json.loads((Path(__file__).resolve().parents[1] / "references/vitaldock.json").read_text(encoding="utf-8"))
COMMANDS = {"check": "check-connection", "activities": "recent-activities", "wellness": "wellness-context"}
STATUSES = {"check": {"connected"}, "activities": {"available", "no_activities"},
            "wellness": {"available", "no_measurements"}}
NEXT = {
    "runtime_missing": "先运行 setup；不接设备也可继续使用训练和营养系统。",
    "incompatible_version": "使用 setup 准备本产品已验证的 VitalDock 版本。",
    "credential_not_configured": "由本人在本机终端运行 authorize，隐藏输入个人 API key；不要发到聊天。",
    "credential_unavailable": "请用运行 Agent 的同一个系统用户运行 authorize。",
    "authentication_failed": "在 Intervals.icu 重新生成个人 API key，再由本人运行 authorize。",
    "access_denied": "检查本人账号与华为连接的授权范围。",
    "network_unavailable": "恢复网络后重新运行原命令；已完成的安装和授权仍可保留。",
    "rate_limited": "按 retry_after_seconds 等待后重试，不连续请求。",
    "wellness_not_granted": "确认用户希望读取恢复指标，再配置相应权限。",
    "timeout": "本次请求超时；确认网络后重试，训练和营养系统仍可使用。",
    "invalid_response": "上游返回不符合已验证的接口，停止使用这次数据。",
    "install_failed": "安装未完成；检查网络和 Python 版本，再运行 setup 继续。",
}


def failure(code: str, **extra) -> dict:
    return {"ok": False, "error": code, "next_step": NEXT.get(code, "检查本机运行环境后重试。"), **extra}


def run(py: Path, home: Path, arguments: list[str], timeout: float):
    try:
        result = subprocess.run([str(py), "-B", "-m", "vitaldock", *arguments], cwd=home,
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, "", '{"message":"timeout"}'
    except OSError:
        return 1, "", '{"message":"runtime_missing"}'


def parse_payload(rc: int, out: str, err: str, command: str) -> dict:
    if rc:
        try:
            error = json.loads(err)
        except (ValueError, TypeError):
            error = {}
        if not isinstance(error, dict):
            error = {}
        message = str(error.get("message") or error.get("error") or "")
        code = message.split(":", 1)[0].strip()
        result = failure(code if code in NEXT else "upstream_failed")
        delay = error.get("retry_after_seconds")
        if isinstance(delay, (int, float)) and not isinstance(delay, bool) and 0 <= delay <= 86400:
            result["retry_after_seconds"] = delay
        return result
    try:
        payload = json.loads(out)
    except (ValueError, TypeError):
        return failure("invalid_response")
    if not isinstance(payload, dict) or payload.get("schema_version") != LOCK["response_schema"] or payload.get("status") not in STATUSES[command]:
        return failure("invalid_response")
    return {**payload, "ok": True}


def python_at(home: Path) -> Path:
    return home / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def managed_home(root: Path) -> Path:
    system.load_config_readonly(root)
    return system.safe_relative(root, "系统/vitaldock", Path("系统/vitaldock"), "设备运行目录")


def runtime(args) -> tuple[Path, Path]:
    if args.root:
        home = managed_home(Path(args.root).expanduser().resolve())
        return home, python_at(home / ".venv")
    explicit = os.environ.get("VITALDOCK_HOME")
    if explicit:
        home = Path(explicit).expanduser().resolve()
        return home, python_at(home / ".venv")
    raise ValueError("请用 --root 指定个人健身系统；开发者也可设置 VITALDOCK_HOME。")


def compatible(py: Path, home: Path, timeout: float) -> bool:
    rc, out, _ = run(py, home, ["--version"], timeout)
    return rc == 0 and out.strip() == LOCK["version"]


def setup(args) -> dict:
    if sys.version_info[:2] < tuple(LOCK["python_min"]):
        return failure("python_version", next_step="设备接入需要 Python 3.11 或以上；训练和营养系统可继续使用。")
    root = Path(args.root).expanduser().resolve()
    home = managed_home(root)
    for relative in ("系统/vitaldock/.venv", "系统/vitaldock/runtime.json", "系统/vitaldock/runtime.json.tmp"):
        system.safe_relative(root, relative, Path("系统/vitaldock"), "设备运行文件")
    system.check_private_path(home)
    marker = home / "runtime.json"
    if home.exists() and any(home.iterdir()) and not marker.is_file():
        return failure("unmanaged_directory", next_step="设备目录已有其他内容，停止安装以保留原件。")
    if marker.exists() and system.read_json(marker).get("component") != "vitaldock":
        return failure("unmanaged_directory", next_step="设备目录的归属标记不匹配，停止安装以保留原件。")
    system.write_json(marker, {"component": "vitaldock", "version": LOCK["version"], "revision": LOCK["revision"]})
    py = python_at(home / ".venv")
    if not py.is_file():
        venv.EnvBuilder(with_pip=True).create(home / ".venv")
    if not compatible(py, home, args.timeout):
        try:
            result = subprocess.run([str(py), "-B", "-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir", "--no-input", LOCK["install"]],
                                    cwd=home, capture_output=True, timeout=max(300, args.timeout))
        except subprocess.TimeoutExpired:
            return failure("install_failed")
        if result.returncode or not compatible(py, home, args.timeout):
            return failure("install_failed")
    return {"ok": True, "stage": "installed", "version": LOCK["version"],
            "next_step": "继续官方账号连接；由本人在本机终端运行 authorize，密钥不会进入聊天。"}


def query(args, command: str, py: Path, home: Path) -> dict:
    argv = [COMMANDS[command], "--day", args.day]
    if command != "check":
        argv += ["--history-days", str(args.history_days)]
    if command == "activities":
        argv += ["--limit", str(args.limit)]
    return parse_payload(*run(py, home, argv, args.timeout), command)


def execute(args) -> dict:
    if args.command == "setup":
        return setup(args)
    home, py = runtime(args)
    if not py.is_file():
        return failure("runtime_missing")
    if not compatible(py, home, args.timeout):
        return failure("incompatible_version", expected_version=LOCK["version"])
    if args.command == "selftest":
        return {"ok": True, "stage": "installed", "version": LOCK["version"], "network_checked": False}
    if args.command == "authorize":
        if not sys.stdin.isatty():
            return failure("credential_not_configured")
        result = subprocess.run([str(py), "-B", "-m", "vitaldock", "connect-intervals"], cwd=home,
                                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        return {"ok": True, "stage": "authorized"} if result.returncode == 0 else failure("authentication_failed")
    if args.command == "onboard":
        checks = {}
        for command in COMMANDS:
            result = query(args, command, py, home)
            checks[command] = {key: result[key] for key in ("ok", "status", "error", "next_step", "retry_after_seconds") if key in result}
            if not result["ok"]:
                return {**result, "stage": command, "checks": checks}
        return {"ok": True, "stage": "verified", "checks": checks,
                "next_step": "连接已验证；无活动或无测量表示当前范围没有可用记录，不能补零或称为未训练。"}
    return query(args, args.command, py, home)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    for command in ("setup", "selftest", "authorize", "onboard", *COMMANDS):
        sub = subs.add_parser(command)
        sub.add_argument("--root", default=os.environ.get("KESHIG_FITNESS_HOME"), required=command == "setup")
        sub.add_argument("--timeout", type=float, default=120)
        sub.add_argument("--day", default=dt.datetime.now().astimezone().date().isoformat())
        sub.add_argument("--history-days", type=int, default=28)
        sub.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        dt.date.fromisoformat(args.day)
        if not 1 <= args.history_days <= 90 or not 1 <= args.limit <= 100 or not 0 < args.timeout <= 600:
            raise ValueError("时间范围、条数或超时超出允许范围")
        result = execute(args)
    except (ValueError, OSError):
        result = failure("invalid_configuration", next_step="检查个人系统目录、日期与运行环境；不需要重新建档。")
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
