"""Verify the VitalDock contract and recoverable setup without credentials or networking."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/training-system/scripts"))
import training_system as system
import vitaldock_client as device


class DeviceTests(unittest.TestCase):
    def test_current_success_and_empty_results_are_not_failures(self):
        for command, statuses in device.STATUSES.items():
            for status in statuses:
                result = device.parse_payload(0, json.dumps({"schema_version": "agent/1", "status": status}), "", command)
                self.assertTrue(result["ok"])
                self.assertEqual(result["status"], status)
        for raw in ("not json", "[]", "{}", '{"schema_version":"agent/2","status":"connected"}'):
            self.assertFalse(device.parse_payload(0, raw, "", "check")["ok"])

    def test_errors_are_actionable_without_echoing_private_output(self):
        private = "SYNTHETIC_PRIVATE_SENTINEL"
        for code in ("authentication_failed", "credential_unavailable", "network_unavailable", "rate_limited", "timeout"):
            result = device.parse_payload(1, private, json.dumps({"message": code + ": " + private, "retry_after_seconds": 30}), "check")
            self.assertEqual(result["error"], code)
            self.assertTrue(result["next_step"])
            self.assertEqual(result["retry_after_seconds"], 30)
            self.assertNotIn(private, json.dumps(result))
        self.assertNotIn(private, json.dumps(device.parse_payload(1, private, private, "check")))

    @unittest.skipIf(sys.version_info < (3, 11), "device setup needs Python 3.11")
    def test_setup_retries_after_failed_install_and_preserves_records(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "personal"
            system.bootstrap(NS(target=str(root)))
            profile = root / "个人训练系统/训练复盘与状态/状态档案/synthetic.md"
            profile.write_text("SYNTHETIC_PRIVATE_RECORD")
            args = NS(root=str(root), timeout=1)

            def create(home):
                py = device.python_at(home)
                py.parent.mkdir(parents=True)
                py.write_text("synthetic executable marker")

            with patch.object(device.venv, "EnvBuilder") as builder, patch.object(device, "compatible", return_value=False), patch.object(device.subprocess, "run", return_value=NS(returncode=1)):
                builder.return_value.create.side_effect = create
                self.assertEqual(device.setup(args)["error"], "install_failed")
            marker = root / "系统/vitaldock/runtime.json"
            self.assertTrue(marker.is_file())
            with patch.object(device, "compatible", side_effect=[False, True]), patch.object(device.subprocess, "run", return_value=NS(returncode=0)) as runner:
                self.assertTrue(device.setup(args)["ok"])
                self.assertIn(device.LOCK["revision"], runner.call_args.args[0][-1])
                self.assertNotIn("-e", runner.call_args.args[0])
            self.assertEqual(profile.read_text(), "SYNTHETIC_PRIVATE_RECORD")

    @unittest.skipIf(sys.version_info < (3, 11), "device setup needs Python 3.11")
    def test_existing_unmanaged_directory_is_preserved(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "personal"
            system.bootstrap(NS(target=str(root)))
            home = root / "系统/vitaldock"
            home.mkdir()
            sentinel = home / "sentinel"
            sentinel.write_text("existing content")
            result = device.setup(NS(root=str(root), timeout=1))
            self.assertEqual(result["error"], "unmanaged_directory")
            self.assertEqual(sentinel.read_text(), "existing content")

    def test_real_subprocess_contract_and_recovery(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            package = home / "vitaldock"
            package.mkdir()
            (package / "__init__.py").write_text("")
            (package / "__main__.py").write_text('''import json,sys
from pathlib import Path
command=sys.argv[1]
if command == '--version':
    print('0.4.0')
elif not Path('authorized').exists():
    print(json.dumps({'error':'ValueError','message':'credential_not_configured'}),file=sys.stderr)
    sys.exit(1)
else:
    status={'check-connection':'connected','recent-activities':'no_activities','wellness-context':'no_measurements'}[command]
    print(json.dumps({'schema_version':'agent/1','status':status}))
''')
            args = NS(command="onboard", root=None, day="2026-11-03", history_days=28, limit=5, timeout=10)
            with patch.dict(os.environ, {"VITALDOCK_HOME": str(home)}), patch.object(device, "python_at", return_value=Path(sys.executable)):
                before = {p.relative_to(home).as_posix(): p.read_bytes() for p in home.rglob("*") if p.is_file()}
                result = device.execute(args)
                self.assertEqual(result["error"], "credential_not_configured")
                (home / "authorized").write_text("synthetic authorization flag")
                result = device.execute(args)
                self.assertTrue(result["ok"])
                self.assertEqual(result["checks"]["activities"]["status"], "no_activities")
                self.assertEqual(result["checks"]["wellness"]["status"], "no_measurements")
                after = {p.relative_to(home).as_posix(): p.read_bytes() for p in home.rglob("*") if p.is_file() and p.name != "authorized"}
                self.assertEqual(before, after)

    def test_noninteractive_authorization_never_reads_a_secret(self):
        args = NS(command="authorize", root=None, timeout=1)
        with patch.object(device, "runtime", return_value=(ROOT, Path(sys.executable))), patch.object(device, "compatible", return_value=True), patch.object(sys.stdin, "isatty", return_value=False), patch.object(device.subprocess, "run") as runner:
            self.assertEqual(device.execute(args)["error"], "credential_not_configured")
            runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
