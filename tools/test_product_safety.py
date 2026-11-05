"""Synthetic tests of data boundaries, publication and an installed user's lifecycle."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_release import build
from privacy_check import audit, check_file
import install

ROOT = Path(__file__).resolve().parents[1]
SYSTEM = ROOT / "skills/training-system/scripts/training_system.py"


def run(*args, cwd=ROOT, expected=0, include_stderr=False):
    result = subprocess.run(list(map(str, args)), cwd=cwd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace",
                            env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    if result.returncode != expected:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout + (result.stderr if include_stderr else "")


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


class ProductSafety(unittest.TestCase):
    def test_source_and_sibling_skill_are_rejected_before_writing(self):
        for target in (ROOT / "data" / "must-not-exist", ROOT / "skills/fitness-plan/new-private"):
            self.assertFalse(target.exists())
            run(sys.executable, SYSTEM, "bootstrap", "--target", target, expected=1)
            self.assertFalse(target.exists())
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw) / "different-checkout"
            source.mkdir()
            (source / "keshig.manifest.json").write_text("{}")
            run(sys.executable, SYSTEM, "bootstrap", "--target", source / "private", expected=1)
            self.assertFalse((source / "private").exists())
            skills = Path(raw) / "another-agent/skills"
            (skills / "existing").mkdir(parents=True)
            (skills / "existing/SKILL.md").write_text("synthetic skill marker")
            run(sys.executable, SYSTEM, "bootstrap", "--target", skills / "new-private", expected=1)
            self.assertFalse((skills / "new-private").exists())

    def test_invalid_output_rejected_before_upgrade_or_migration(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "personal"
            run(sys.executable, SYSTEM, "bootstrap", "--target", root)
            config = root / "系统/keshig-system.json"
            value = json.loads(config.read_text(encoding="utf-8"))
            value["output_locations"]["plans"] = "../outside"
            value["skills_root"] = "old-path"
            config.write_text(json.dumps(value), encoding="utf-8")
            before = snapshot(root)
            for command in ("inspect", "validate", "upgrade", "doctor"):
                run(sys.executable, SYSTEM, command, "--root", root, expected=1)
                self.assertEqual(snapshot(root), before)

    def test_output_junction_cannot_escape_personal_root(self):
        if os.name != "nt":
            self.skipTest("Windows junction regression")
        from test_installer import create_junction, remove_junction
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "personal"
            outside = Path(raw) / "outside"
            outside.mkdir()
            run(sys.executable, SYSTEM, "bootstrap", "--target", root)
            link = root / "redirected"
            create_junction(link, outside)
            try:
                config = root / "系统/keshig-system.json"
                value = json.loads(config.read_text(encoding="utf-8"))
                value["output_locations"]["plans"] = "redirected"
                config.write_text(json.dumps(value), encoding="utf-8")
                run(sys.executable, SYSTEM, "upgrade", "--root", root, expected=1)
                self.assertEqual(list(outside.iterdir()), [])
            finally:
                remove_junction(link)

    def test_shared_default_keeps_agent_entry_junction(self):
        with tempfile.TemporaryDirectory() as raw, patch.object(Path, "home", return_value=Path(raw)), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(install.default_agent_root("codex"), Path(raw) / ".agents")
            if os.name != "nt":
                return
            from test_installer import create_junction, remove_junction
            shared = Path(raw) / ".agents/skills"
            shared.mkdir(parents=True)
            entry = Path(raw) / ".codex/skills"
            entry.parent.mkdir()
            create_junction(entry, shared)
            try:
                with patch.dict(os.environ, {"CODEX_HOME": str(entry.parent)}):
                    target = install.default_agent_root("codex")
                    self.assertEqual(target, shared.parent)
                    install.validate_agent_layout(target, ["training-system"])
                self.assertTrue(install.is_reparse_point(entry))
            finally:
                remove_junction(entry)

    def test_installed_lifecycle_preserves_all_user_records(self):
        with tempfile.TemporaryDirectory(prefix="keshig-new-user-") as raw:
            temp = Path(raw)
            agent, root = temp / "agent", temp / "我的健身系统"
            run(sys.executable, ROOT / "tools/install.py", "--target-root", agent)
            system = agent / "skills/training-system/scripts/training_system.py"
            run(sys.executable, system, "bootstrap", "--target", root)
            config_path = root / "系统/keshig-system.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            locations = config["output_locations"]
            plan = root / locations["plans"] / "synthetic-plan.json"
            shutil.copyfile(ROOT / "skills/fitness-plan/references/plan-contract.example.json", plan)
            run(sys.executable, agent / "skills/fitness-plan/scripts/validate_plan.py", plan)
            nutrition = root / locations["nutrition"] / "synthetic-nutrition.json"
            shutil.copyfile(ROOT / "skills/nutrition-system/assets/examples/nutrition-contract.example.json", nutrition)
            run(sys.executable, agent / "skills/nutrition-system/scripts/validate_nutrition_contract.py", nutrition)
            for name, text in {
                locations["profiles"] + "/synthetic-profile.md": "# 虚构测试档案\n体重：未知\n",
                locations["reviews"] + "/synthetic-review.md": "# 虚构复盘\n实际训练数据：待填写\n",
                locations["reviews"] + "/INDEX.md": "- synthetic-review.md\n",
                "个人训练系统/训练复盘与状态/当前执行基准/基准.md": "当前计划：synthetic-plan.json\n",
                "健身知识库/私人知识包/synthetic.txt": "SYNTHETIC_PRIVATE_CONTENT\n",
            }.items():
                (root / name).write_text(text, encoding="utf-8")
            before = snapshot(root)
            summary = json.loads(run(sys.executable, system, "inspect", "--root", root))
            self.assertTrue(summary["current_plans"])
            run(sys.executable, ROOT / "tools/upgrade.py", "--root", root, "--agent-root", agent, "--apply")
            self.assertEqual(snapshot(root), before)
            moved = temp / "迁移后的系统"
            shutil.move(str(root), str(moved))
            run(sys.executable, system, "doctor", "--root", moved)
            run(sys.executable, system, "validate", "--root", moved)
            self.assertEqual(snapshot(moved), before)

    def test_staged_secrets_and_deleted_history_are_checked(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            run("git", "init", root)
            secret = "sk-" + "synthetic_credential_1234567890"
            (root / "README.md").write_text(secret)
            run("git", "add", "README.md", cwd=root)
            (root / "README.md").write_text("safe worktree")
            errors, _ = audit(root, "staged")
            self.assertTrue(errors)
            self.assertNotIn(secret, "\n".join(errors))
            run("git", "add", "README.md", cwd=root)
            (root / "plans").mkdir()
            (root / "plans/private.json").write_text('{"synthetic": true}')
            run("git", "add", "plans/private.json", cwd=root)
            run("git", "-c", "user.name=Keshig Test", "-c", "user.email=test@example.invalid", "commit", "-m", "synthetic fixture", cwd=root)
            run("git", "rm", "plans/private.json", cwd=root)
            run("git", "-c", "user.name=Keshig Test", "-c", "user.email=test@example.invalid", "commit", "-m", "remove fixture", cwd=root)
            self.assertFalse(audit(root, "worktree")[0])
            self.assertTrue(audit(root, "history")[0])

    def test_local_hook_blocks_commit_and_recovers_after_correction(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            run("git", "init", root)
            (root / "tools").mkdir()
            for name in ("privacy_check.py", "setup_dev.py", "install.py"):
                shutil.copyfile(ROOT / "tools" / name, root / "tools" / name)
            shutil.copytree(ROOT / ".githooks", root / ".githooks")
            run(sys.executable, root / "tools/setup_dev.py", cwd=root)
            (root / "README.md").write_text("sk-" + "synthetic_credential_1234567890")
            run("git", "add", "README.md", cwd=root)
            args = ("git", "-c", "user.name=Keshig Test", "-c", "user.email=test@example.invalid", "commit", "-m", "synthetic hook test")
            result = run(*args, cwd=root, expected=1, include_stderr=True)
            self.assertIn("privacy_check: FAIL", result)
            (root / "README.md").write_text("synthetic public example")
            run("git", "add", "README.md", cwd=root)
            run(*args, cwd=root)
            with tempfile.TemporaryDirectory() as remote_raw:
                remote = Path(remote_raw) / "local-test.git"
                run("git", "init", "--bare", remote)
                run("git", "push", str(remote), "HEAD:refs/heads/test", cwd=root)
                (root / "README.md").write_text("sk-" + "synthetic_credential_1234567890")
                run("git", "add", "README.md", cwd=root)
                run("git", "-c", "core.hooksPath=disabled-test-hooks", *args[1:], cwd=root)
                result = run("git", "push", str(remote), "HEAD:refs/heads/test", cwd=root, expected=1, include_stderr=True)
                self.assertIn("privacy_check: FAIL", result)

    def test_release_excludes_ignored_files_and_blocks_unknown_files(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "source"
            root.mkdir()
            run("git", "init", root)
            (root / "README.md").write_text("synthetic public documentation")
            (root / "keshig.manifest.json").write_text('{"version":"0.0.0"}')
            (root / ".gitignore").write_text("data/\nrelease-output/\n")
            (root / "data").mkdir()
            (root / "data/private.json").write_text("SYNTHETIC_PRIVATE_SENTINEL")
            output = root / "release-output/keshig.zip"
            build(root, output)
            with zipfile.ZipFile(output) as archive:
                self.assertFalse(any("private" in name for name in archive.namelist()))
            self.assertTrue(check_file("unexpected/README.md", b"text"))
            self.assertTrue(check_file("docs/photo.jpg", b"synthetic image"))
            self.assertTrue(check_file("schema/health.sqlite3", b"synthetic database"))
            self.assertTrue(check_file("skills/fitness-plan/plans/private.json", b"{}"))


if __name__ == "__main__":
    unittest.main()
