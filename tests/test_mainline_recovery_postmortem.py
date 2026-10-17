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
        responses = [
            result("List of devices attached\nexampledevice\trecovery\n\n"),
            result("0\n"), result("recovery\n"), result("3.7.1\n")]
        with mock.patch.object(m.subprocess, "run", side_effect=responses) as run:
            o = m.check_recovery("adb")
        self.assertEqual(o["mode"], "recovery")
        self.assertEqual(o["adb_transport"], "recovery")
        self.assertTrue(o["twrp_version_present"])
        self.assertEqual(run.call_count, 4)
        self.assertEqual(run.call_args_list[1].args[0], ["adb", "shell", "id", "-u"])
        self.assertEqual(run.call_args_list[2].args[0],
                         ["adb", "shell", "getprop", "ro.bootmode"])

    def test_twrp_version_accepts_missing_bootmode(self):
        responses = [
            result("List of devices attached\nexampledevice\tdevice\n"),
            result("0\n"), result("\n"), result("3.7.1\n")]
        with mock.patch.object(m.subprocess, "run", side_effect=responses):
            self.assertTrue(m.check_recovery("adb")["twrp_version_present"])

    def test_unknown_bootmode_accepted_when_adb_reports_recovery(self):
        responses = [
            result("List of devices attached\r\nexampledevice\trecovery\r\n\r\n"),
            result("0\n"), result("unknown\n"), result("\n")]
        with mock.patch.object(m.subprocess, "run", side_effect=responses):
            check = m.check_recovery("adb")
        self.assertEqual(check["mode"], "unknown")
        self.assertEqual(check["adb_transport"], "recovery")
        self.assertFalse(check["twrp_version_present"])

    def test_regular_android_rejected(self):
        responses = [
            result("List of devices attached\nexampledevice\tdevice\n"),
            result("0\n"), result("normal\n"), result("\n")]
        with mock.patch.object(m.subprocess, "run", side_effect=responses):
            with self.assertRaisesRegex(ValueError, "do not confirm recovery"):
                m.check_recovery("adb")

    def test_non_root_rejected(self):
        responses = [
            result("List of devices attached\nexampledevice\trecovery\n"),
            result("2000\n")]
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

    def test_getprop_failure_identifies_command(self):
        responses = [
            result("List of devices attached\nexampledevice\trecovery\n"),
            result("0\n"),
            m.subprocess.CompletedProcess(["adb", "shell", "getprop"], 1, "", "offline")]
        with mock.patch.object(m.subprocess, "run", side_effect=responses):
            with self.assertRaisesRegex(ValueError, "adb shell getprop returned exit 1"):
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

    def test_missing_pstore_still_allows_last_kmsg(self):
        responses = [
            m.subprocess.CompletedProcess(["adb", "shell", "ls"], 1, "", "No such file"),
            result("0\n")]
        with mock.patch.object(m.subprocess, "run", side_effect=responses) as run:
            self.assertEqual(m.enumerate_pstore("adb"), [])
        self.assertEqual(run.call_args_list[0].args[0],
                         ["adb", "shell", "ls", "-1", "/sys/fs/pstore"])

    def test_pstore_list_does_not_use_nested_shell(self):
        with mock.patch.object(m.subprocess, "run",
                               return_value=result("console-ramoops-0\n")) as run:
            self.assertEqual(m.enumerate_pstore("adb"), ["console-ramoops-0"])
        self.assertEqual(run.call_args.args[0],
                         ["adb", "shell", "ls", "-1", "/sys/fs/pstore"])


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

    def test_remote_cat_error_text_is_not_counted_as_last_kmsg(self):
        import io
        class FakePopen:
            def __init__(self, payload):
                self.stdout = io.BytesIO(payload)
            def wait(self, timeout):
                return 0
            def poll(self):
                return 0
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            bogus = b"cat: /proc/last_kmsg: No such file or directory\n"
            with mock.patch.object(m.subprocess, "Popen",
                                   return_value=FakePopen(bogus)):
                with self.assertRaisesRegex(ValueError, "not a kernel log"):
                    m.read_file("adb", "/proc/last_kmsg", path, "last_kmsg")
            self.assertFalse((path / "last_kmsg.log").exists())

    def test_legacy_419_console_is_not_612_boot_evidence(self):
        import io
        class FakePopen:
            def __init__(self, payload):
                self.stdout = io.BytesIO(payload)
            def wait(self, timeout):
                return 0
            def poll(self):
                return 0
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            old = (b"[0] Linux version 4.19.325-test\n"
                   b"[57] reboot: Power down\n[57] Powering off the SoC\n")
            with mock.patch.object(m.subprocess, "Popen",
                                   return_value=FakePopen(old)):
                item = m.read_file("adb", "/sys/fs/pstore/console-ramoops-0",
                                   p, "console-ramoops-0")
            self.assertTrue(item["contains_legacy_linux_419_banner"])
            self.assertFalse(item["contains_linux_612_banner"])
            self.assertFalse(item["contains_test_init_marker"])

    def test_mainline_612_marker_detectable(self):
        import io
        class FakePopen:
            def __init__(self, payload):
                self.stdout = io.BytesIO(payload)
            def wait(self, timeout):
                return 0
            def poll(self):
                return 0
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            new = (b"Linux version 6.12.0-test\n"
                   b"UMI612-MINIMAL-INIT: PID1 reached\n")
            with mock.patch.object(m.subprocess, "Popen",
                                   return_value=FakePopen(new)):
                item = m.read_file("adb", "/sys/fs/pstore/console-ramoops-0",
                                   p, "console-ramoops-0")
            self.assertTrue(item["contains_linux_612_banner"])
            self.assertTrue(item["contains_test_init_marker"])
            self.assertFalse(item["contains_legacy_linux_419_banner"])

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
