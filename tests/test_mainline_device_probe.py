"""P0b 只读 ADB 采集安全契约与输出解析回归。"""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch
import subprocess

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mainline_device_probe", ROOT / "scripts/mainline_device_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def fixture(device="umi", skip_end=False):
    rows = []
    for section in probe.SECTIONS:
        rows.append(f"{probe.START}{section}__")
        if section == "device":
            rows.append(device)
        elif section == "dt_compatible":
            rows += ["qcom,kona-mtp", "qcom,kona"]
        elif section == "partition_names":
            rows += ["boot", "dtbo", "vendor", "system"]
        elif section == "kernel":
            rows += ["4.19.325-test"]
    if not skip_end:
        rows.append(probe.END)
    return "\n".join(rows) + "\n"


class DeviceProbeTests(unittest.TestCase):
    def test_parses_complete_fixture(self):
        d = probe.parse_sections(fixture())
        report = probe.build_report(d)
        self.assertEqual(report["device"], "umi")
        self.assertEqual(report["dt_compatible"], ["qcom,kona", "qcom,kona-mtp"])
        self.assertIn("dtbo", report["partition_names"])
        self.assertFalse(report["safe_to_flash"])
        self.assertFalse(report["first_boot_test"])

    def test_rejects_wrong_device(self):
        with self.assertRaisesRegex(ValueError, "仅支持 umi"):
            probe.build_report(probe.parse_sections(fixture(device="dagu")))

    def test_rejects_truncated_output(self):
        with self.assertRaisesRegex(ValueError, "不完整"):
            probe.parse_sections(fixture(skip_end=True))

    def test_empty_list_is_not_missing_hardware(self):
        report = probe.build_report(probe.parse_sections(fixture()))
        self.assertEqual(report["ufs_hosts"], [])
        self.assertIn("未知", report["limitations"])

    def test_no_sensitive_collections_or_mutations(self):
        script = probe.DEVICE_SCRIPT
        for forbidden in ("ro.serialno", "android_id", "/proc/cmdline", "su -c",
                          "flash ", "fastboot", "dd if=", "getprop |", "setprop ",
                          "mount -", "chmod ", "chown ", "ro.boot.serialno"):
            self.assertNotIn(forbidden, script)

    def test_command_uses_unprivileged_shell(self):
        process = subprocess.CompletedProcess(
            args=["adb", "shell", "sh"], returncode=0, stdout=fixture(), stderr=""
        )
        with patch.object(probe.subprocess, "run", return_value=process) as run:
            report = probe.probe("adb")
        self.assertEqual(report["device"], "umi")
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["adb", "shell", "sh"])
        self.assertIn("input", kwargs)
        self.assertFalse(kwargs["check"])

    def test_duplicate_section_refused(self):
        original = fixture()
        extra = f"{probe.START}device__\n"
        with self.assertRaisesRegex(ValueError, "异常"):
            probe.parse_sections(original.replace(f"{probe.START}model__", extra + f"{probe.START}model__"))

    def test_incomplete_older_versions_rejected(self):
        bad = fixture().replace(f"{probe.START}device__", f"{probe.START}device_wrong__")
        with self.assertRaises(ValueError):
            probe.parse_sections(bad)
