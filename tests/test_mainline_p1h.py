"""P1h static source, real observed pstore summary, and sanitized-report tests."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("p1h", ROOT / "scripts/mainline_p1h_pstore_audit.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class P1hTests(unittest.TestCase):
    def setUp(self):
        self.g = json.loads(m.GRAPH.read_text(encoding="utf-8"))
        self.p1g = json.loads(m.P1G.read_text(encoding="utf-8"))

    def check(self):
        return m.validate(self.g, self.p1g)

    @staticmethod
    def synthetic_p1g():
        return {
            "schema_version": 1, "stage": "P1g", "device": "umi",
            "source": "explicit non-root read-only adb shell",
            "observed_kernel": "4.19.325-cip131-st15-perf",
            "non_ab_observed": True,
            "pstore_directory_present": True,
            "pstore_filesystem_mounted": True,
            "pstore_record_types_visible": ["console", "pmsg"],
            "pstore_survives_crash_verified": False,
            "earlycon_verified": False, "recovery_path_tested": False,
            "safe_to_attempt_mainline_boot": False, "safe_to_flash": False,
            "writes_to_device": False,
            "note": "mount/record presence is not evidence of retained crash logs or wired UART",
        }

    def test_observed_summary(self):
        r = self.check()
        self.assertTrue(r["pstore_mounted_legacy_419"])
        self.assertEqual(r["record_classes_seen"], ["console", "pmsg"])
        self.assertFalse(r["pstore_crash_survival_proven"])
        self.assertFalse(r["safe_to_flash"])

    def test_user_report_not_claimed_inspected(self):
        self.assertFalse(self.g["evidence"]["full_local_p1g_json_inspected"])

    def test_reject_flash_flag(self):
        self.g["gates"]["safe_to_flash"] = True
        with self.assertRaisesRegex(ValueError, "unsafe boot"):
            self.check()

    def test_reject_boot_permission(self):
        self.g["gates"]["safe_to_attempt_mainline_boot"] = True
        with self.assertRaisesRegex(ValueError, "unsafe boot"):
            self.check()

    def test_reject_assumed_ramoops_address(self):
        self.g["mainline_ramoops_requirements"]["umi_reserved_phandle"] = "res_xbl_uefi_log"
        with self.assertRaisesRegex(ValueError, "layout/size"):
            self.check()

    def test_reject_memory_buffer_guess(self):
        self.g["mainline_ramoops_requirements"]["umi_buffer_sizes"] = {"console": 8192}
        with self.assertRaisesRegex(ValueError, "layout/size"):
            self.check()

    def test_reject_crash_retention_claim(self):
        self.g["evidence"]["crash_survival_tested"] = True
        with self.assertRaisesRegex(ValueError, "runtime proof"):
            self.check()

    def test_reject_real_device_backend_claim(self):
        self.g["evidence"]["pstore_backend_name_confirmed_from_platform_device"] = True
        with self.assertRaisesRegex(ValueError, "runtime proof"):
            self.check()

    def test_reject_dmesg_absence_interpretation(self):
        self.g["interpretation"]["absence_of_dmesg_file_proves_unsupported_backend"] = True
        with self.assertRaisesRegex(ValueError, "interpretation"):
            self.check()

    def test_report_validates(self):
        self.assertTrue(m.verify_local_p1g_report(self.synthetic_p1g(), self.g))

    def test_report_rejects_unexpected_record_class(self):
        r = self.synthetic_p1g()
        r["pstore_record_types_visible"].append("dmesg")
        with self.assertRaisesRegex(ValueError, "does not match"):
            m.verify_local_p1g_report(r, self.g)

    def test_report_rejects_private_extra(self):
        r = self.synthetic_p1g()
        r["serial"] = "not-allowed"
        with self.assertRaisesRegex(ValueError, "key whitelist"):
            m.verify_local_p1g_report(r, self.g)

    def test_report_rejects_unsafe_claim(self):
        r = self.synthetic_p1g()
        r["recovery_path_tested"] = True
        with self.assertRaisesRegex(ValueError, "unsafe P1g"):
            m.verify_local_p1g_report(r, self.g)

    def test_report_rejects_other_kernel(self):
        r = self.synthetic_p1g()
        r["observed_kernel"] = "6.12.1"
        with self.assertRaisesRegex(ValueError, "legacy 4.19"):
            m.verify_local_p1g_report(r, self.g)

    def test_report_rejects_other_device(self):
        r = self.synthetic_p1g()
        r["device"] = "elish"
        with self.assertRaisesRegex(ValueError, "identity"):
            m.verify_local_p1g_report(r, self.g)

    def test_source_checks_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "implementation drift"):
            m.verify_upstream("", "")

    def test_p1g_gate_remains_false(self):
        self.assertFalse(self.p1g["gates"]["safe_to_attempt_mainline_boot"])
        self.assertFalse(self.p1g["gates"]["safe_to_flash"])

if __name__ == "__main__":
    unittest.main()
