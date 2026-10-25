"""Protect other processes and prevent competing windowless clock workers."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
if sys.platform == "win32":
    import clock_service


@unittest.skipUnless(sys.platform == "win32", "Windows background service")
class ClockServiceTests(unittest.TestCase):
    def test_stale_pid_cannot_target_an_unrelated_python_process(self):
        pid_file = Mock()
        pid_file.read_text.return_value = "1234"
        process = Mock()
        process.cmdline.return_value = ["python.exe", "other-app.py", "clock", "--quiet"]
        with patch.object(clock_service, "WORKER_PID", pid_file), \
                patch("clock_service.psutil.Process", return_value=process):
            self.assertIsNone(clock_service.clock_process())

    def test_recognizes_only_this_projects_clock_command(self):
        pid_file = Mock()
        pid_file.read_text.return_value = "1234"
        process = Mock()
        process.cmdline.return_value = [
            "python.exe", "-u", str(clock_service.SHOW), "clock", "--quiet"]
        with patch.object(clock_service, "WORKER_PID", pid_file), \
                patch("clock_service.psutil.Process", return_value=process):
            self.assertIs(clock_service.clock_process(), process)

    def test_worker_started_before_rename_is_still_recognized(self):
        missing = Mock()
        missing.read_text.side_effect = FileNotFoundError
        legacy = Mock()
        legacy.read_text.return_value = "1234"
        process = Mock()
        process.cmdline.return_value = [
            "python.exe", "-u", str(clock_service.SHOW), "clock", "--quiet"]
        with patch.object(clock_service, "WORKER_PID", missing), \
                patch.object(clock_service, "LEGACY_WORKER_PID", legacy), \
                patch("clock_service.psutil.Process", return_value=process):
            self.assertIs(clock_service.clock_process(), process)

    def test_another_runner_cannot_take_lock_until_release(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(clock_service, "RUNTIME", Path(folder)):
            with clock_service.runner_lock() as first:
                self.assertTrue(first)
                with clock_service.runner_lock() as second:
                    self.assertFalse(second)
            with clock_service.runner_lock() as after_release:
                self.assertTrue(after_release)


if __name__ == "__main__":
    unittest.main()
