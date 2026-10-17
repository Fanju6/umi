"""TWRP recovery postmortem tool: mocked ADB only, no real device."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "pm", HERE / "scripts/mainline_recovery_postmortem.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def result(text):
    return m.subprocess.CompletedProcess(["adb"], 0, text, "")

class RecoveryPostmortemTests(unittest.TestCase):
    def test_twrp_mode_and_root(self):
        responses = [result("List of devices attached\nexampledevice\trecovery\n\n"),
                     result("MODE=recovery\nTWRP=3.7.1\nUID=0\n")]
        with mock.patch.object(m.subprocess, "run", side_effect=responses) as run:
            o = m.check_recovery("adb")
        self.assertEqual(o["mode"], "recovery")
        self.assertEqual(o["adb_transport"], "recovery")
        self.assertTrue(o["twrp_version_present"])
        self.assertEqual(run.call_count, 2)

    def test_twrp_version_accepts_missing_bootmode(self):
        responses = [result("List of devices attached\nexampledevice\tdevice\n"),
                     result("MODE=\nTWRP=3.7.1\nUID=0\n")]
        with mock.patch.object(m.subprocess, "run", side_effect=responses):
            self.assertTrue(m.check_recovery("adb")["twrp_version_present"])

    def test_unknown_bootmode_accepted_when_adb_reports_recovery(self):
        responses = [result("List of devices attached\r\nexampledevice\trecovery\r\n\r\n"),
                     result("MODE=unknown\nTWRP=\nUID=0\n")]
        with mock.patch.object(m.subprocess, "run", side_effect=responses):
            check = m.check_recovery("adb")
        self.assertEqual(check["mode"], "unknown")
        self.assertEqual(check["adb_transport"], "recovery")
        self.assertFalse(check["twrp_version_present"])

    def test_regular_android_rejected(self):
        responses = [result("List of devices attached\nexampledevice\tdevice\n"),
                     result("MODE=normal\nTWRP=\nUID=0\n")]
        with mock.patch.object(m.subprocess, "run", side_effect=responses):
            with self.assertRaisesRegex(ValueError, "do not confirm recovery"):
                m.check_recovery("adb")

    def test_non_root_rejected(self):
        responses = [result("List of devices attached\nexampledevice\trecovery\n"),
                     result("MODE=unknown\nTWRP=\nUID=2000\n")]
        with mock.patch.object(m.subprocess, "run", side_effect=responses):
            with self.assertRaisesRegex(ValueError, "not root"):
                m.check_recovery("adb")

    def test_multiple_transports_rejected(self):
        listing = "List of devices attached\nexampledevice\trecovery\notherdevice\tdevice\n"
        with mock.patch.object(m.subprocess, "run", return_value=result(listing)) as run:
            with self.assertRaisesRegex(ValueError, "exactly one"):
                m.check_recovery("adb")
            run.assert_called_once()

    def test_no_adb_device_rejected(self):
        with mock.patch.object(m.subprocess, "run",
                               return_value=result("List of devices attached\n\n")):
            with self.assertRaisesRegex(ValueError, "exactly one"):
                m.check_recovery("adb")

    def test_whitelist_not_private_filenames(self):
        self.assertTrue(m.ALLOW.fullmatch("console-ramoops-0"))
        self.assertTrue(m.ALLOW.fullmatch("pmsg-ramoops-0"))
        self.assertFalse(m.ALLOW.fullmatch("../../../data/misc"))
        self.assertFalse(m.ALLOW.fullmatch("serial_number"))
        self.assertFalse(m.ALLOW.fullmatch("not-relevant"))

    def test_enumerate_filters_unknown(self):
        raw = "console-ramoops-0\nsecret-file\ndmesg-ramoops-0\npmsg-ramoops-0\n"
        with mock.patch.object(m.subprocess, "run", return_value=result(raw)):
            values = m.enumerate_pstore("adb")
        self.assertEqual(values, ["console-ramoops-0", "dmesg-ramoops-0",
                                  "pmsg-ramoops-0"])

    def test_capture_recovery_no_logs(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(m, "check_recovery",
                               return_value={"mode": "recovery", "twrp_version_present": True}), \
             mock.patch.object(m, "enumerate_pstore", return_value=[]), \
             mock.patch.object(m, "read_file", side_effect=ValueError("not readable")):
            out = Path(td) / "summary.json"
            rawdir = Path(td) / "raw"
            report = m.capture("adb", rawdir, out)
            self.assertTrue(out.exists())
            self.assertEqual(report["captured"], [])
            self.assertFalse(report["linux_612_boot_log_found"])
            self.assertIn("last_kmsg", report["not_captured"])

    def test_safety_paths_in_code(self):
        import inspect
        code = inspect.getsource(m)
        self.assertIn("exec-out", code)
        self.assertIn("cat", code)
        self.assertNotIn("fastboot flash", code)
        self.assertNotIn("sysrq-trigger", code)
        self.assertNotIn("reboot bootloader", code)

    def test_logs_are_private_by_default(self):
        self.assertTrue(m.TAG.startswith("UMI612"))
        self.assertEqual(m.MAX_SINGLE, 8 * 1024 * 1024)
        self.assertTrue(m.MAX_FILES <= 32)

if __name__ == "__main__":
    unittest.main()
