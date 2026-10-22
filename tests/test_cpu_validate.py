import importlib
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch


class CpuValidationTests(unittest.TestCase):
    def test_unsupported_environment_records_failure_without_launching_processes(self):
        from scripts import cpu_validate

        with TemporaryDirectory() as directory:
            with (
                patch.object(cpu_validate.platform, "system", return_value="Windows"),
                patch.object(
                    cpu_validate.platform, "platform", return_value="test platform"
                ),
                patch.object(cpu_validate.subprocess, "Popen") as popen,
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(cpu_validate.main(["--output", directory]), 1)
            result = json.loads((Path(directory) / "summary.json").read_text())
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["environment"], "test platform")
            self.assertIn("Linux and pidstat", result["error"])
            self.assertIn("server/handlers.py", result["source_sha256"])
            popen.assert_not_called()

    def test_failed_client_connection_closes_socket(self):
        from scripts import cpu_validate

        sock = Mock()
        sock.connect.side_effect = OSError("connection refused")
        with patch.object(cpu_validate.socket, "socket", return_value=sock):
            with self.assertRaisesRegex(OSError, "connection refused"):
                cpu_validate.Client("CpuAlice")
        sock.close.assert_called_once()

    def test_import_uses_project_root_without_creating_output_directory(self):
        original = Path.cwd()
        with TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                module = importlib.import_module("scripts.cpu_validate")
                importlib.reload(module)
                self.assertEqual(module.ROOT, Path(__file__).resolve().parents[1])
                self.assertEqual(list(Path(directory).iterdir()), [])
            finally:
                os.chdir(original)

    def test_cpu_samples_follow_header_and_pid_instead_of_executable_name(self):
        from scripts.cpu_validate import cpu_samples

        output = """Linux example
# Time UID PID %usr %system %guest %wait %CPU CPU Command
12:00:01 1000 42 0.00 0.00 0.00 0.00 0.25 0 python3.14
12:00:02 1000 42 0.00 0.00 0.00 0.00 0.50 0 python
12:00:02 1000 99 0.00 0.00 0.00 0.00 99.00 0 other
"""
        self.assertEqual(cpu_samples(output, 42), [0.25, 0.5])

    def test_cpu_samples_accept_older_pidstat_column_layout(self):
        from scripts.cpu_validate import cpu_samples

        output = """# Time UID PID %usr %system %guest %CPU CPU Command
12:00:01 PM 1000 42 0.00 0.00 0.00 0.75 0 python3
"""
        self.assertEqual(cpu_samples(output, 42), [0.75])
