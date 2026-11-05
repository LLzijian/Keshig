#!/usr/bin/env python3
"""Validate a Keshig strength-training-review Markdown file against frontmatter and structure specs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_FRONTMATTER_KEYS = (
    "title",
    "date",
    "week",
    "training_day",
    "review_mode",
    "status",
    "source_type",
    "source_ref",
    "progression_basis",
    "plan",
    "external_source",
)

ALLOWED_REVIEW_MODES = {"cycle", "rolling", "baseline", "weekly"}
ALLOWED_STATUSES = {"已复盘", "待补全"}
ALLOWED_SOURCE_TYPES = {"external_record", "chat", "local"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TOKEN_LEAK_RE = re.compile(r"(ntn_[A-Za-z0-9]+|secret_[A-Za-z0-9]+|Bearer\s+[A-Za-z0-9._-]+|ghp_[A-Za-z0-9]+)")

SINGLE_SESSION_REQUIRED_HEADERS = (
    "复盘模式与依据",
    "本次判定",
    "个人体感与记录澄清",
    "恢复与干扰",
    "下一次训练",
    "待确认调整",
    "待补全记录与已沉淀",
)

WEEKLY_REQUIRED_HEADERS = (
    "总训练目标与当前水平",
    "当前周期及本周进度",
    "主项表现与严格执行度",
    "个人体感与记录澄清",
    "执行偏差、重复问题与是否调整",
    "本周沉淀的关键决策",
    "下一周执行重点与待补数据",
    "周结论",
)


def parse_frontmatter_and_body(text: str) -> tuple[dict[str, str] | None, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        return None, text

    fm: dict[str, str] = {}
    for line in lines[1:end_idx]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        k, v = stripped.split(":", 1)
        val = v.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        fm[k.strip()] = val
    body = "\n".join(lines[end_idx + 1 :])
    return fm, body


def validate_review_text(text: str, *, require_confirmed: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    fm, body = parse_frontmatter_and_body(text)
    if fm is None:
        return {
            "valid": False,
            "can_modify_plan": False,
            "errors": ["missing YAML frontmatter block delimited by ---"],
            "warnings": [],
        }

    for k in REQUIRED_FRONTMATTER_KEYS:
        if k not in fm:
            errors.append(f"missing required frontmatter key: {k}")

    for k in ("title", "date", "week", "training_day", "review_mode", "status", "source_type", "source_ref"):
        if k in fm and not fm[k].strip():
            errors.append(f"frontmatter.{k} must be non-empty")

    if "date" in fm and fm["date"] and not DATE_RE.match(fm["date"]):
        errors.append("frontmatter.date must match YYYY-MM-DD")

    mode = fm.get("review_mode", "")
    if mode not in ALLOWED_REVIEW_MODES:
        errors.append(f"frontmatter.review_mode must be one of {sorted(ALLOWED_REVIEW_MODES)}")

    status = fm.get("status", "")
    if status not in ALLOWED_STATUSES:
        errors.append(f"frontmatter.status must be one of {sorted(ALLOWED_STATUSES)}")

    source_type = fm.get("source_type", "")
    if source_type not in ALLOWED_SOURCE_TYPES:
        errors.append(f"frontmatter.source_type must be one of {sorted(ALLOWED_SOURCE_TYPES)}")

    if mode in {"rolling", "baseline"} and fm.get("week") not in {"无周期", ""}:
        warnings.append("rolling/baseline review usually sets frontmatter.week to '无周期'")

    if source_type == "external_record" and not fm.get("external_source", "").strip():
        errors.append("frontmatter.external_source must be non-empty when source_type is external_record")

    for secret_field in ("source_ref", "external_source"):
        val = fm.get(secret_field, "")
        if TOKEN_LEAK_RE.search(val):
            errors.append(f"frontmatter.{secret_field} contains a raw token/credential pattern")

    required_headers = WEEKLY_REQUIRED_HEADERS if mode == "weekly" else SINGLE_SESSION_REQUIRED_HEADERS
    for hdr in required_headers:
        if hdr not in body:
            errors.append(f"missing required review section heading: '{hdr}'")

    if mode in {"rolling", "baseline"} and "渐进方式检查" not in body:
        errors.append("rolling/baseline single-session review must include section '渐进方式检查'")

    can_modify_plan = (status == "已复盘") and not errors
    if status == "待补全":
        if require_confirmed:
            errors.append("review status is '待补全' (subjective feedback or clarification pending); cannot be used as confirmed basis to modify plan")
        else:
            warnings.append("review status is '待补全'; saved as factual draft only and cannot authorize plan modifications")

    return {
        "valid": not errors,
        "status": status,
        "review_mode": mode,
        "can_modify_plan": can_modify_plan,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_md", type=Path, help="Path to review Markdown file")
    parser.add_argument("--require-confirmed", action="store_true", help="Fail if review status is 待补全")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    try:
        content = args.review_md.read_text(encoding="utf-8")
    except Exception as exc:
        if args.json_output:
            print(json.dumps({"valid": False, "errors": [f"failed to read file: {exc}"], "warnings": []}, ensure_ascii=False, indent=2))
        else:
            print(f"ERROR: failed to read file: {exc}", file=sys.stderr)
        return 1

    res = validate_review_text(content, require_confirmed=args.require_confirmed)
    if args.json_output:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        for err in res["errors"]:
            print(f"ERROR: {err}")
        for warn in res["warnings"]:
            print(f"WARNING: {warn}")
        if res["valid"]:
            print(f"VALID: review structure passed (status={res['status']}, can_modify_plan={res['can_modify_plan']})")
    return 0 if res["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
