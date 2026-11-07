#!/usr/bin/env python3
"""Portable bootstrap, doctor, inspect, upgrade and validation commands for Keshig System.

Keshig 不生成网页、不维护面板。系统根目录只是一棵可移动的文件树：
配置、状态档案、计划、周期、复盘与营养记录各归其位，全部由 Agent 在对话中读写。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

SUITE_VERSION = "0.4.0"
PORTABLE_CONFIG_VERSION = 1
PROJECT_RELATIVE = Path("个人训练系统")
BACKUP_RELATIVE = Path("系统/backups")
RUNTIME_SKILLS = "@runtime"
WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
CORE_SKILLS = (
    "fitness-plan",
    "strength-cycle-planner",
    "strength-training-review",
    "training-return",
    "training-expert-library",
    "nutrition-system",
)
OUTPUT_LOCATIONS = {
    "profiles": "个人训练系统/训练复盘与状态/状态档案",
    "plans": "个人训练系统/训练与周期/当前周期",
    "cycles": "个人训练系统/训练与周期/力量周期",
    "reviews": "个人训练系统/训练复盘与状态/训练复盘",
    "returns": "个人训练系统/训练复盘与状态/状态档案",
    "nutrition": "个人训练系统/饮食与营养",
}
REQUIRED_DIRS = (
    "个人训练系统/训练与周期/当前周期",
    "个人训练系统/训练与周期/力量周期",
    "个人训练系统/训练复盘与状态/训练复盘",
    "个人训练系统/训练复盘与状态/状态档案",
    "个人训练系统/训练复盘与状态/当前执行基准",
    "个人训练系统/饮食与营养",
    "健身知识库/专家系统",
    "健身知识库/来源登记",
    "健身知识库/私人知识包",
)
HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent.parent
ADOPTABLE_DATA_ENTRIES = {
    "health.db",
    "health.db-wal",
    "health.db-shm",
    "health.db-journal",
    "sheet_mirror.json",
    "schema.sql",
    "schema_device.sql",
    "backups",
}


def stop(message: str) -> None:
    raise SystemExit("training_system: FAIL\n- " + message)


def default_data_root() -> Path | None:
    """Resolve the default personal data root (<agent_root>/data) when running from an installed Skill."""
    for env_key in ("KESHIG_FITNESS_HOME", "KESHIG_DATA_ROOT"):
        env_val = os.environ.get(env_key, "").strip()
        if env_val:
            return Path(env_val).expanduser().resolve()
    agent_root = SKILL_ROOT.parent.resolve()
    if (agent_root / "keshig.manifest.json").is_file() or (agent_root / "SKILL.md").is_file():
        return None
    for parent in (agent_root, *agent_root.parents):
        if (parent / "keshig.manifest.json").is_file() or (parent / "SKILL.md").is_file():
            return None
    return agent_root / "data"


def resolve_root(raw: str | None, flag: str = "--root") -> Path:
    if raw and str(raw).strip():
        return Path(raw).expanduser().resolve()
    default = default_data_root()
    if default is not None:
        return default
    stop(f"未指定 {flag}，且当前处于源码树内无法使用默认 <agent_root>/data；请显式传入 {flag}")
    raise AssertionError("unreachable")


def check_private_path(path: Path) -> Path:
    target = path.expanduser().resolve()
    skills = SKILL_ROOT.resolve()
    if target == skills or skills in target.parents:
        stop("个人资料必须放在已安装的 skills 目录之外")
    for parent in (target, *target.parents):
        skill_root = parent.name.casefold() == "skills" and (
            parent.parent.name in {".agents", ".codex", ".claude"} or next(parent.glob("*/SKILL.md"), None) is not None)
        if skill_root or (parent / "keshig.manifest.json").is_file() or (parent / "SKILL.md").is_file():
            stop("个人资料必须放在 Keshig 源码和 Skill 目录之外")
    return target


def check_data_paths(root: Path, data: dict | None = None) -> None:
    check_private_path(root)
    values = [*REQUIRED_DIRS, "系统", BACKUP_RELATIVE.as_posix()]
    if data:
        locations = data.get("output_locations")
        if not isinstance(locations, dict):
            stop("output_locations 必须是对象")
        if any(not isinstance(value, str) or not value.strip() or is_machine_absolute(value) for value in locations.values()):
            stop("output_locations 必须使用当前个人系统内的非空相对路径")
        values.extend(str(value) for value in locations.values())
        values.extend(str(data.get(key) or fallback) for key, fallback in (
            ("project_root", PROJECT_RELATIVE), ("backup_root", BACKUP_RELATIVE)))
    for value in values:
        target = safe_relative(root, value, PROJECT_RELATIVE, "数据位置")
        check_private_path(target)
    if config_path(root).resolve().parent != (root / "系统").resolve():
        stop("系统配置不能指向其他目录")


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        stop(f"配置无法读取：{path}（{exc}）")
    if not isinstance(data, dict):
        stop(f"配置根节点必须是对象：{path}")
    return data


def write_json(path: Path, data: dict) -> None:
    check_private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    if path.is_symlink() or temporary.is_symlink():
        stop("拒绝通过文件链接写入个人资料")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_text(path: Path, content: str) -> None:
    check_private_path(path)
    if path.is_symlink():
        stop("拒绝通过文件链接写入个人资料")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config_path(root: Path) -> Path:
    return root / "系统" / "keshig-system.json"


def portable_relative(path: Path, root: Path, field: str) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        stop(f"{field} 必须位于当前系统根目录内：{path}")
    return relative.as_posix()


def is_machine_absolute(value: object) -> bool:
    text = str(value or "")
    return Path(text).is_absolute() or bool(WINDOWS_ABSOLUTE.match(text)) or text.startswith(("\\\\", "//"))


def safe_relative(root: Path, raw: object, fallback: Path, field: str) -> Path:
    """Resolve a portable config path and reject absolute paths or traversal."""
    value = str(raw or fallback.as_posix())
    candidate = Path(value)
    if is_machine_absolute(value):
        candidate = fallback
    target = (root / candidate).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        stop(f"配置 {field} 越出当前系统根目录")
    return target


def migrate_config(root: Path, path: Path, data: dict) -> dict:
    """Convert legacy machine paths to current-root-relative values in place."""
    desired_project = PROJECT_RELATIVE.as_posix()
    desired_backup = BACKUP_RELATIVE.as_posix()
    changed = False

    project_value = str(data.get("project_root") or "")
    project_candidate = Path(project_value) if project_value else None
    if not project_candidate or is_machine_absolute(project_value):
        data["project_root"] = desired_project
        changed = True
    else:
        resolved = safe_relative(root, project_value, PROJECT_RELATIVE, "project_root")
        portable = portable_relative(resolved, root, "project_root")
        if portable != project_value.replace("\\", "/"):
            data["project_root"] = portable
            changed = True

    if data.get("skills_root") != RUNTIME_SKILLS:
        data["skills_root"] = RUNTIME_SKILLS
        changed = True

    backup_value = str(data.get("backup_root") or "")
    backup_candidate = Path(backup_value) if backup_value else None
    if not backup_candidate or is_machine_absolute(backup_value):
        data["backup_root"] = desired_backup
        changed = True
    else:
        resolved = safe_relative(root, backup_value, BACKUP_RELATIVE, "backup_root")
        portable = portable_relative(resolved, root, "backup_root")
        if portable != backup_value.replace("\\", "/"):
            data["backup_root"] = portable
            changed = True

    if data.get("portable_config_version") != PORTABLE_CONFIG_VERSION:
        data["portable_config_version"] = PORTABLE_CONFIG_VERSION
        changed = True

    if changed:
        migration_root = root / BACKUP_RELATIVE / "config-migrations"
        migration_root.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
        shutil.copy2(path, migration_root / ("keshig-system-before-portability-" + stamp + ".json"))
        data["paths_migrated_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        write_json(path, data)
        print("配置路径已迁移为可移动相对路径")
    return data


def load_config(root: Path) -> dict:
    check_data_paths(root)
    path = config_path(root)
    if not path.is_file():
        stop("找不到系统配置；请先在空目录运行 bootstrap，或用 --root 指向已有系统")
    data = read_json(path)
    if data.get("schema") != 1:
        stop(f"不支持的配置 schema：{data.get('schema')}")
    check_data_paths(root, data)
    return migrate_config(root, path, data)


def load_config_readonly(root: Path) -> dict:
    check_data_paths(root)
    path = config_path(root)
    if not path.is_file():
        stop("找不到系统配置；请先在空目录运行 bootstrap，或用 --root 指向已有系统")
    data = read_json(path)
    if data.get("schema") != 1:
        stop(f"不支持的配置 schema：{data.get('schema')}")
    check_data_paths(root, data)
    data = dict(data)
    project_value = str(data.get("project_root") or "")
    if not project_value or is_machine_absolute(project_value):
        data["project_root"] = PROJECT_RELATIVE.as_posix()
    return data


def project_path(root: Path, config: dict) -> Path:
    return safe_relative(root, config.get("project_root"), PROJECT_RELATIVE, "project_root")


def backup_path(root: Path, config: dict) -> Path:
    return safe_relative(root, config.get("backup_root"), BACKUP_RELATIVE, "backup_root")


def ensure_empty(target: Path) -> None:
    if not target.exists():
        return
    entries = [p.name for p in target.iterdir()]
    if not entries:
        return
    if (target / "系统" / "keshig-system.json").exists() or (target / "INDEX.md").exists():
        stop("目标目录已初始化 Keshig 系统，请用 doctor / upgrade 或 --root：" + str(target))
    non_adoptable = [name for name in entries if name not in ADOPTABLE_DATA_ENTRIES]
    if non_adoptable:
        stop("bootstrap 只允许空目录或仅含现有 health.db 的数据目录，拒绝覆盖已有内容：" + str(target))


def installed_skills() -> Path:
    if not SKILL_ROOT.is_dir():
        stop("Skill 根目录不可用：" + str(SKILL_ROOT))
    return SKILL_ROOT


def bootstrap(args: argparse.Namespace) -> None:
    root = resolve_root(getattr(args, "target", None), "--target")
    check_data_paths(root)
    ensure_empty(root)
    root.mkdir(parents=True, exist_ok=True)
    adopted_existing_db = (root / "health.db").is_file()

    for relative in REQUIRED_DIRS:
        (root / relative).mkdir(parents=True, exist_ok=True)

    stamp = dt.date.today().isoformat()
    files = {
        "INDEX.md": (
            "# Keshig 健身系统\n\n"
            f"- 建档日期：{stamp}\n"
            "- 交互方式：直接和 Agent 对话，本系统不生成网页。\n\n"
            "## 目录\n\n"
            "- `个人训练系统/训练复盘与状态/状态档案`：建档快照与身体状态\n"
            "- `个人训练系统/训练与周期/当前周期`：当前训练计划\n"
            "- `个人训练系统/训练与周期/力量周期`：单项力量周期\n"
            "- `个人训练系统/训练复盘与状态/训练复盘`：单次与周复盘\n"
            "- `个人训练系统/训练复盘与状态/当前执行基准`：当前执行口径\n"
            "- `个人训练系统/饮食与营养`：营养契约与记录\n"
            "- `健身知识库/`：可复用知识、专家模块与来源登记\n"
        ),
        "健身知识库/README.md": (
            "# 健身知识库\n\n"
            "这里只保存可复用训练知识、来源登记与专家模块；"
            "私人资料放入 `私人知识包`，默认不参与公开导出。\n"
        ),
        "健身知识库/知识索引.md": (
            "# 知识索引\n\n- [[专家系统/README|专家系统]]\n- [[来源登记/README|来源登记]]\n"
        ),
        "健身知识库/专家系统/README.md": (
            "# 专家系统\n\n"
            "按需接入训练金字塔、增肌、营养、力量、动作模式与运动医学模块；"
            "医学危险信号优先转介。\n"
        ),
        "健身知识库/来源登记/README.md": (
            "# 来源登记\n\n"
            "登记来源、适用边界、审核日期与公开/仅本地范围；不复制受版权保护原文。\n"
        ),
        "健身知识库/私人知识包/README.md": (
            "# 私人知识包\n\n"
            "存放用户自己的书摘、课程笔记与私人资料；不会被导出或提交到公开仓库。\n"
        ),
    }
    for relative, content in files.items():
        write_text(root / relative, content)

    config = {
        "schema": 1,
        "suite_version": SUITE_VERSION,
        "project_root": PROJECT_RELATIVE.as_posix(),
        "skills_root": RUNTIME_SKILLS,
        "backup_root": BACKUP_RELATIVE.as_posix(),
        "database_path": "health.db" if adopted_existing_db else "系统/health.sqlite3",
        "portable_config_version": PORTABLE_CONFIG_VERSION,
        "output_locations": OUTPUT_LOCATIONS,
        "created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "managed_files": {
            relative: sha256(root / relative)
            for relative in ("INDEX.md", "健身知识库/README.md", "健身知识库/知识索引.md")
        },
    }
    write_json(config_path(root), config)
    import health_db
    if adopted_existing_db:
        health_db.migrate_db(root)
    health_db.init_db(root)
    print("training_system: PASS")
    print("mode: 待建档；请完成问诊后再生成正式计划")
    print("root: " + str(root))


def doctor(args: argparse.Namespace) -> None:
    root = resolve_root(getattr(args, "root", None))
    config = load_config(root)
    problems: list[str] = []

    for relative in REQUIRED_DIRS:
        if not (root / relative).is_dir():
            problems.append("目录缺失：" + relative)

    skills = installed_skills()
    for name in CORE_SKILLS:
        if not (skills / name / "SKILL.md").is_file():
            problems.append("Skill 缺失或未安装：" + name)

    project = project_path(root, config)
    if not project.is_dir():
        problems.append("个人训练系统目录缺失：" + str(project))

    for key in ("profiles", "plans", "cycles", "reviews", "returns", "nutrition"):
        value = str((config.get("output_locations") or {}).get(key) or "")
        if not value:
            problems.append("output_locations 缺少：" + key)
        elif is_machine_absolute(value):
            problems.append("output_locations 含机器绝对路径：" + key)

    import health_db
    problems.extend(health_db.verify_db_readonly(root))

    if problems:
        print("training_system: FAIL")
        for item in problems:
            print("- " + item)
        raise SystemExit(1)

    print("training_system: PASS")
    print("config: " + str(config_path(root)))
    print("project: " + str(project))
    print("skills: " + ", ".join(CORE_SKILLS))


def _listed(directory: Path, pattern: str, limit: int = 20) -> list[str]:
    if not directory.is_dir():
        return []
    rows = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.relative_to(directory.parent.parent).as_posix() for p in rows[:limit]]


def inspect_system(args: argparse.Namespace) -> None:
    """Print a compact summary of the current system without loading计划正文."""
    root = resolve_root(getattr(args, "root", None))
    config = load_config_readonly(root)
    locations = config.get("output_locations") or {}

    def locate(key: str) -> Path:
        return safe_relative(root, locations.get(key), Path("个人训练系统"), key)

    import health_db

    summary = {
        "kind": "keshig_system_summary",
        "root": str(root),
        "suite_version": config.get("suite_version"),
        "project_root": str(project_path(root, config)),
        "authoritative_sources": {
            key: str(locate(key)) for key in ("profiles", "plans", "cycles", "reviews", "returns", "nutrition")
        },
        "database": health_db.inspect_db_readonly(root),
        "current_plans": _listed(locate("plans"), "*"),
        "current_cycles": _listed(locate("cycles"), "*"),
        "recent_reviews": _listed(locate("reviews"), "*"),
        "recent_profiles": _listed(locate("profiles"), "*"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def install_skill(args: argparse.Namespace) -> None:
    root = resolve_root(getattr(args, "root", None))
    load_config(root)
    name = args.name
    source = installed_skills() / name
    if not (source / "SKILL.md").is_file():
        stop("未找到可安装的 Skill：" + name)
    print("Skill 已就绪：" + str(source))
    print("提示：Skill 由套件统一安装；此处只做可用性检查，不复制文件。")


def import_private_pack(args: argparse.Namespace) -> None:
    root = resolve_root(getattr(args, "root", None))
    config = load_config(root)
    source = Path(args.source).resolve()
    if not source.is_dir():
        stop("源目录不存在：" + str(source))
    target = root / "健身知识库" / "私人知识包" / source.name
    safe_relative(root, target.relative_to(root).as_posix(), PROJECT_RELATIVE, "私人知识包")
    check_private_path(target)
    if target.exists():
        stop("目标已存在，拒绝覆盖：" + str(target))
    shutil.copytree(source, target)
    print("已导入私人知识包：" + str(target))
    print("注意：私人知识包只用于本地判断，不参与公开导出。")


def upgrade(args: argparse.Namespace) -> None:
    root = resolve_root(getattr(args, "root", None))
    config = load_config(root)
    config["suite_version"] = SUITE_VERSION
    write_json(config_path(root), config)
    import health_db
    if health_db.db_path(root).is_file() and health_db.verify_db_readonly(root):
        health_db.init_db(root)
    print("training_system: PASS")
    print("配置已升级到 " + SUITE_VERSION)
    print("计划、复盘、状态档案与营养记录保持不变")


def validate_system(args: argparse.Namespace) -> None:
    root = resolve_root(getattr(args, "root", None))
    config = load_config_readonly(root)
    problems: list[str] = []

    if config.get("schema") != 1:
        problems.append("配置 schema 不是 1")
    locations = config.get("output_locations") or {}
    for key in ("profiles", "plans", "cycles", "reviews", "returns", "nutrition"):
        if not str(locations.get(key) or ""):
            problems.append("output_locations 缺少：" + key)

    for relative in REQUIRED_DIRS:
        if not (root / relative).is_dir():
            problems.append("目录缺失：" + relative)

    import health_db
    problems.extend(health_db.verify_db_readonly(root))

    if problems:
        print("training_system: FAIL")
        for item in problems:
            print("- " + item)
        raise SystemExit(1)

    print("training_system: PASS")
    print("validate: 配置、目录与输出位置一致")


def main() -> None:
    parser = argparse.ArgumentParser(description="Keshig 本地系统管理（纯文件，无网页）")
    subs = parser.add_subparsers(dest="command", required=True)

    p = subs.add_parser("bootstrap")
    p.add_argument("--target", default=None, help="个人数据目录（默认 <agent_root>/data）")
    p.set_defaults(func=bootstrap)

    p = subs.add_parser("doctor")
    p.add_argument("--root", default=None, help="个人数据目录（默认 <agent_root>/data）")
    p.set_defaults(func=doctor)

    p = subs.add_parser("inspect")
    p.add_argument("--root", default=None, help="个人数据目录（默认 <agent_root>/data）")
    p.set_defaults(func=inspect_system)

    p = subs.add_parser("upgrade")
    p.add_argument("--root", default=None, help="个人数据目录（默认 <agent_root>/data）")
    p.set_defaults(func=upgrade)

    p = subs.add_parser("install-skill")
    p.add_argument("--root", default=None, help="个人数据目录（默认 <agent_root>/data）")
    p.add_argument("--name", required=True)
    p.set_defaults(func=install_skill)

    p = subs.add_parser("import-private-pack")
    p.add_argument("--root", default=None, help="个人数据目录（默认 <agent_root>/data）")
    p.add_argument("--source", required=True)
    p.set_defaults(func=import_private_pack)

    p = subs.add_parser("validate")
    p.add_argument("--root", default=None, help="个人数据目录（默认 <agent_root>/data）")
    p.set_defaults(func=validate_system)

    p = subs.add_parser("check-path")
    p.add_argument("--path", required=True)
    p.set_defaults(func=lambda args: print("private_path: PASS " + str(check_private_path(Path(args.path)))))

    p = subs.add_parser("db-init")
    p.add_argument("--root", default=None, help="个人数据目录（默认 <agent_root>/data）")

    def _db_init(args: argparse.Namespace) -> None:
        root = resolve_root(getattr(args, "root", None))
        load_config_readonly(root)
        import health_db
        path = health_db.init_db(root)
        print("training_system: PASS")
        print("database: " + str(path))

    p.set_defaults(func=_db_init)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
