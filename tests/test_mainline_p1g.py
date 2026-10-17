"""P1g recovery/early-log evidence gates, no real-device test execution."""
import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

audit = module("audit", "scripts/mainline_p1g_recovery_audit.py")
probe = module("probe", "scripts/mainline_p1g_log_probe.py")
SAMPLE = """__UMI_P1G_DEVICE__
umi
__UMI_P1G_KERNEL__
4.19.325-cip131-st15-perf
__UMI_P1G_BOOT_COMPLETE__
1
__UMI_P1G_AB_UPDATE__
false
__UMI_P1G_SLOT_SUFFIX__
__UMI_P1G_PSTORE_DIR__
yes
__UMI_P1G_PSTORE_FS__
no
__UMI_P1G_PSTORE_KINDS__
console
dmesg
"""

class P1gTests(unittest.TestCase):
    def setUp(self):
        self.g = json.loads(audit.GRAPH.read_text(encoding="utf-8"))
        self.p1e = json.loads(audit.P1E.read_text(encoding="utf-8"))

    def check(self):
        return audit.validate(self.g, self.p1e)

    def test_baseline(self):
        outcome = self.check()
        self.assertTrue(outcome["non_ab_layout_supported"])
        self.assertFalse(outcome["recovery_restoration_proven"])
        self.assertFalse(outcome["safe_to_flash"])

    def test_header_observation_not_full_boot_image_parse(self):
        self.assertEqual(self.g["legacy_device_evidence"]["boot_header_version_reported"], 2)
        self.assertFalse(self.g["legacy_device_evidence"]["boot_header_image_parsed_in_this_stage"])

    def test_reject_claimed_recovery_success(self):
        self.g["gates"]["recovery_boot_verified"] = True
        with self.assertRaisesRegex(ValueError, "unsafe recovery gate"):
            self.check()

    def test_reject_false_pstore_claim(self):
        self.g["source_evidence"]["xbl_log_proves_pstore"] = True
        with self.assertRaisesRegex(ValueError, "logging capability"):
            self.check()

    def test_reject_uart_pad_assumption(self):
        self.g["source_evidence"]["uart_pad_mapping_confirmed"] = True
        with self.assertRaisesRegex(ValueError, "logging capability"):
            self.check()

    def test_reject_hardcoded_verified_earlycon(self):
        self.g["runtime_logging"]["uart_earlycon_verified"] = True
        with self.assertRaisesRegex(ValueError, "untested logging"):
            self.check()

    def test_reject_fabricated_restoration(self):
        self.g["legacy_device_evidence"]["known_good_restore_tested"] = True
        with self.assertRaisesRegex(ValueError, "recovery capability"):
            self.check()

    def test_reject_flash_permission(self):
        self.g["gates"]["safe_to_flash"] = True
        with self.assertRaisesRegex(ValueError, "unsafe recovery gate"):
            self.check()

    def test_reject_unsafe_boot_attempt(self):
        self.g["gates"]["safe_to_attempt_mainline_boot"] = True
        with self.assertRaisesRegex(ValueError, "unsafe recovery gate"):
            self.check()

    def test_reject_slot_a_assumption(self):
        self.g["legacy_device_evidence"]["slot_suffix"] = "_a"
        with self.assertRaisesRegex(ValueError, "non-A/B"):
            self.check()

    def test_source_set_must_have_two_legacy_uart_labels(self):
        self.assertEqual(len(self.g["source_evidence"]["vendor_common_enabled_uarts"]), 2)

    def test_probe_parse(self):
        report = probe.parse(SAMPLE)
        self.assertTrue(report["non_ab_observed"])
        self.assertTrue(report["pstore_directory_present"])
        self.assertFalse(report["pstore_filesystem_mounted"])
        self.assertEqual(report["pstore_record_types_visible"], ["console", "dmesg"])
        self.assertFalse(report["safe_to_flash"])
        self.assertFalse(report["writes_to_device"])

    def test_probe_empty_pstore_files_is_not_recovery_proof(self):
        report = probe.parse(SAMPLE.replace("console\ndmesg\n", ""))
        self.assertEqual(report["pstore_record_types_visible"], [])
        self.assertFalse(report["pstore_survives_crash_verified"])

    def test_probe_rejects_other_device(self):
        with self.assertRaisesRegex(ValueError, "not umi"):
            probe.parse(SAMPLE.replace("\numi\n", "\ndagu\n", 1))

    def test_probe_rejects_ab_device(self):
        with self.assertRaisesRegex(ValueError, "non-A/B"):
            probe.parse(SAMPLE.replace("__UMI_P1G_AB_UPDATE__\nfalse",
                                       "__UMI_P1G_AB_UPDATE__\ntrue"))

    def test_probe_rejects_extra_record_data(self):
        with self.assertRaisesRegex(ValueError, "classification"):
            probe.parse(SAMPLE + "serial-number-should-not-be-captured\n")

    def test_probe_rejects_missing_markers(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            probe.parse(SAMPLE.split("__UMI_P1G_PSTORE_FS__")[0])

    def test_probe_device_script_read_only(self):
        self.assertIn("getprop ro.product.device", probe.DEVICE_SCRIPT)
        self.assertIn("/sys/fs/pstore", probe.DEVICE_SCRIPT)
        self.assertNotRegex(probe.DEVICE_SCRIPT,
                            r"\b(?:su|dd|cat|reboot|fastboot|setprop|mkfs|mount)\b")
        self.assertNotIn(">/dev/", probe.DEVICE_SCRIPT)
        self.assertNotIn(">/sys/", probe.DEVICE_SCRIPT)

if __name__ == "__main__":
    unittest.main()
