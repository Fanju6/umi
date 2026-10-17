"""Simulated Root DTBO/debugfs follow-up; CI never connects to device."""
import importlib.util
import json
import struct
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "root_followup", ROOT / "scripts/mainline_root_targeted_followup.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def words(data):
    return " ".join("%02x" % b for b in data)

def dtbo_bytes():
    return struct.pack(">8I", 0xd7b7ab1e, 1300, 32, 32, 3, 32, 2048, 0) + bytes(32)

def sample(raw=None):
    if raw is None:
        raw = dtbo_bytes()
    return "\n".join([
        "__UMI_EXTRA_ID__|umi|4.19.325-test|0",
        "__UMI_EXTRA_DEBUG__|unmounted",
        "__UMI_EXTRA_SUMMARY__|sys_kernel_debug|unavailable",
        "__UMI_EXTRA_SUMMARY__|d|readable",
        "__UMI_EXTRA_DTBO__|" + words(raw),
        "__UMI_EXTRA_END__", "",
    ])

class RootTargetedTests(unittest.TestCase):
    def test_official_big_endian_dtbo(self):
        d = m.parse(sample())
        self.assertEqual(d["dtbo_header"]["format"], "android_dt_table")
        self.assertEqual(d["dtbo_header"]["magic_hex"], "d7b7ab1e")
        self.assertEqual(d["dtbo_header"]["dt_table"]["entry_count"], 3)
        self.assertTrue(d["dtbo_header"]["dt_table"]["basic_structure_plausible"])
        self.assertFalse(d["safe_to_flash"])
        self.assertFalse(d["recovery_boot_tested"])

    def test_magic_little_endian_is_not_accepted_as_standard(self):
        raw = bytes.fromhex("1eabb7d7") + bytes(60)
        self.assertEqual(m.inspect_dtbo(words(raw))["format"], "unidentified")

    def test_qcdt_candidate(self):
        self.assertEqual(m.inspect_dtbo(words(b"QCDT" + bytes(60)))["format"],
                         "qualcomm_qcdt_candidate")

    def test_raw_fdt(self):
        self.assertEqual(m.inspect_dtbo(words(bytes.fromhex("d00dfeed") + bytes(60)))
                         ["format"], "raw_fdt_candidate")

    def test_dtbo_unreadable(self):
        self.assertFalse(m.inspect_dtbo("unavailable")["readable"])

    def test_reject_wrong_device(self):
        with self.assertRaisesRegex(ValueError, "device/kernel/root"):
            m.parse(sample().replace("umi|4.19", "dada|4.19"))

    def test_reject_non_root(self):
        with self.assertRaisesRegex(ValueError, "device/kernel/root"):
            m.parse(sample().replace("4.19.325-test|0", "4.19.325-test|2000"))

    def test_reject_truncated_header(self):
        with self.assertRaisesRegex(ValueError, "64-byte"):
            m.parse(sample(raw=dtbo_bytes()[:16]))

    def test_no_mount_or_write_in_script(self):
        for bad in ("mount -t", "mount -o", "fastboot", "setprop",
                    "of=", "reboot", "sysrq-trigger", "echo 1 >"):
            self.assertNotIn(bad, m.SHELL)
        self.assertIn("bs=64 count=1", m.SHELL)

    def test_unknown_dtbo_not_corrupt_claim(self):
        d = m.parse(sample(raw=bytes([0x12]*64)))
        self.assertEqual(d["dtbo_header"]["format"], "unidentified")
        self.assertFalse(d["safe_to_attempt_mainline_boot"])

    def test_summary_paths_are_not_full_content(self):
        d = m.parse(sample())
        self.assertTrue(d["debugfs"]["paths"]["d"] == "readable")
        self.assertEqual(set(d["debugfs"]["paths"]),
                         {"d", "sys_kernel_debug"})

    def test_preflight_wrong_device_no_root_run(self):
        called = []
        def fake_run(args, **kwargs):
            called.append(args)
            return m.subprocess.CompletedProcess(args, 0, "dada\n", "")
        with mock.patch.object(m.subprocess, "run", side_effect=fake_run):
            with self.assertRaisesRegex(ValueError, "not umi"):
                m.collect("adb")
        self.assertEqual(len(called), 1)

if __name__ == "__main__":
    unittest.main()
