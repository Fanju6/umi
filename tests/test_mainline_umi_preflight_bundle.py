"""One-shot umi preflight tests: synthetic Root output and files only (no ADB)."""
import importlib.util
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "preflight", ROOT / "scripts/mainline_umi_preflight_bundle.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def report():
    return "\n".join([
        "ID|umi|4.19.325-cip131-test|false||0|1",
        "SEC|orange|unlocked|0",
        "PART|boot|present|67108864",
        "PART|recovery|present|67108864",
        "PART|dtbo|present|8388608",
        "PART|vbmeta|present|65536",
        "PART|vbmeta_system|missing|0",
        "PART|vendor_boot|missing|0",
        "PART|super|present|1048576000",
        "MOUNT|pstore|yes",
        "MOUNT|debugfs|no",
        "PSTORE|dmesg", "PSTORE|console",
        "RAMOOPS|mem_address|0xB0000000",
        "RAMOOPS|mem_size|4194304",
        "CFG|CONFIG_PSTORE=y",
        "CFG|CONFIG_DEBUG_FS=y",
        "CMD|loglevel=3",
        "END", "",
    ])

class PreflightTests(unittest.TestCase):
    def test_expected_one_shot_metadata(self):
        v = m.parse(report())
        self.assertEqual(v["kernel"], "4.19.325-cip131-test")
        self.assertTrue(v["parts"]["boot"]["present"])
        self.assertIsNone(v["parts"]["vendor_boot"]["size_bytes"])
        self.assertEqual(v["kernel_config"]["CONFIG_DEBUG_FS"], "y")
        self.assertEqual(v["ramoops"]["mem_size"], "4194304")
        self.assertEqual(v["pstore_kinds"], ["console", "dmesg"])

    def test_root_required(self):
        with self.assertRaisesRegex(ValueError, "Root"):
            m.parse(report().replace("false||0|1", "false||2000|1"))

    def test_non_ab_required(self):
        with self.assertRaisesRegex(ValueError, "non-A/B"):
            m.parse(report().replace("false||0|1", "true|_a|0|1"))

    def test_fail_closed_missing_partition(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            m.parse(report().replace("PART|recovery|present|67108864\n", ""))

    def test_extra_partition_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid partition"):
            m.parse(report().replace("PART|super", "PART|userdata"))

    def test_private_cmdline_not_accepted(self):
        with self.assertRaisesRegex(ValueError, "unapproved"):
            m.parse(report().replace("CMD|loglevel=3", "CMD|androidboot.serialno=PRIVATE"))

    def test_no_raw_pstore_accepted(self):
        with self.assertRaisesRegex(ValueError, "invalid pstore"):
            m.parse(report().replace("PSTORE|console", "PSTORE|SECRET"))

    def test_missing_end_rejected(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            m.parse(report().replace("END", ""))

    def test_boot_v2_header_only(self):
        with tempfile.TemporaryDirectory() as td:
            b = bytearray(1660)
            b[:8] = b"ANDROID!"
            struct.pack_into("<I", b, 8, 18432)
            struct.pack_into("<I", b, 16, 10240)
            struct.pack_into("<I", b, 36, 4096)
            struct.pack_into("<I", b, 40, 2)
            b[64:80] = b"PRIVATE CMD DATA"
            f = Path(td) / "boot.img"
            f.write_bytes(b)
            result = m.read_header(f, "boot")
            self.assertEqual(result["header_version"] if "header_version" in result
                             else result["version"], 2)
            self.assertEqual(result["kernel_bytes"], 18432)
            self.assertNotIn("PRIVATE", str(result))

    def test_dtbo_v0_header(self):
        with tempfile.TemporaryDirectory() as td:
            b = bytearray(1660)
            struct.pack_into(">I", b, 0, 0xd7b7ab1e)
            struct.pack_into(">I", b, 4, 5514578)
            struct.pack_into(">I", b, 16, 12)
            f = Path(td) / "dtbo.img"
            f.write_bytes(b)
            self.assertEqual(m.read_header(f, "dtbo")["entries"], 12)

    def test_dtbo_magic_wrong_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "dtbo.img"
            p.write_bytes(bytes(1660))
            with self.assertRaisesRegex(ValueError, "DTBO"):
                m.read_header(p, "dtbo")

    def test_no_unsafe_device_operations(self):
        src = m.SHELL
        for forbidden in ("fastboot", "setprop ", "reboot", "mount -t",
                          "sysrq-trigger", "dd of=", "echo 1 >"):
            self.assertNotIn(forbidden, src)
        import inspect
        action = inspect.getsource(m.backup)
        self.assertIn("dd if=", action)
        self.assertNotIn("dd of=", action)

    def test_wrong_device_preflight_stops_root(self):
        calls = []
        def fake(*a, **kw):
            calls.append(a)
            return m.subprocess.CompletedProcess(a, 0, "dagu\n", "")
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(m.subprocess, "run", side_effect=fake):
            with self.assertRaisesRegex(ValueError, "wrong device"):
                m.collect("adb", Path(td) / "report.json", Path(td) / "backups")
        self.assertEqual(len(calls), 1)

    def test_no_backup_size_guess(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "size"):
                m.backup("adb", "boot", 0, Path(td))

if __name__ == "__main__":
    unittest.main()
