"""P1i P0c absence versus runtime ramoops probe: fail-closed offline tests."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

a = load("p1i_audit", "scripts/mainline_p1i_ramoops_audit.py")
p = load("p1i_probe", "scripts/mainline_p1i_ramoops_probe.py")

SAMPLE = """__UMI_P1I_DEVICE__
umi
__UMI_P1I_KERNEL__
4.19.325-cip131-st15-perf
__UMI_P1I_BOOT_COMPLETE__
1
__UMI_P1I_AB_UPDATE__
false
__UMI_P1I_SLOT_SUFFIX__
__UMI_P1I_PSTORE_MOUNT__
yes
__UMI_P1I_PLATFORM_RAMOOPS__
yes
__UMI_P1I_DT_RAMOOPS__
no
__UMI_P1I_MODULE_PARAMS__
no
"""

class P1iTests(unittest.TestCase):
    def setUp(self):
        self.g = json.loads(a.GRAPH.read_text(encoding="utf-8"))
        self.p0c = json.loads(a.P0C.read_text(encoding="utf-8"))
        self.p1h = json.loads(a.P1H.read_text(encoding="utf-8"))

    def validate(self):
        return a.validate(self.g, self.p0c, self.p1h)

    def test_baseline(self):
        result = self.validate()
        self.assertEqual(result["p0c_nodes_reviewed"], 34)
        self.assertEqual(result["p0c_named_ramoops"], 0)
        self.assertFalse(result["ramoops_backend_mapping_verified"])
        self.assertFalse(result["safe_to_flash"])

    def test_p0c_no_named_ramoops_does_not_prove_absent_backend(self):
        self.assertFalse(self.g["evidence"]["named_ramoops_absence_proves_no_backend"])
        self.assertEqual(self.g["evidence"]["backend_registration_method"], None)

    def test_reject_fabricated_physical_address(self):
        self.g["evidence"]["physical_address"] = "0x80880000"
        with self.assertRaisesRegex(ValueError, "unverified Pstore"):
            self.validate()

    def test_reject_blind_uefi_ramoops_reuse(self):
        self.g["evidence"]["backend_registration_method"] = "XBL region"
        with self.assertRaisesRegex(ValueError, "unverified Pstore"):
            self.validate()

    def test_reject_false_negative_from_missing_ramoops_node(self):
        self.g["evidence"]["named_ramoops_absence_proves_no_backend"] = True
        with self.assertRaisesRegex(ValueError, "unverified Pstore"):
            self.validate()

    def test_reject_flash_gate(self):
        self.g["gates"]["safe_to_flash"] = True
        with self.assertRaisesRegex(ValueError, "unsafe P1i"):
            self.validate()

    def test_reject_boot_gate(self):
        self.g["gates"]["safe_to_attempt_mainline_boot"] = True
        with self.assertRaisesRegex(ValueError, "unsafe P1i"):
            self.validate()

    def test_reject_probe_physical_reg_reads(self):
        self.g["next_probe"]["reads_dt_reg_values"] = True
        with self.assertRaisesRegex(ValueError, "probe safety"):
            self.validate()

    def test_detect_new_p0c_ramoops_name(self):
        self.p0c["regions"]["fixed"][0]["node"] = "ramoops@80000000"
        with self.assertRaisesRegex(ValueError, "re-review"):
            self.validate()

    def test_realistic_probe_parse(self):
        r = p.parse(SAMPLE)
        self.assertTrue(r["ramoops_platform_device_name_observed"])
        self.assertFalse(r["ramoops_dt_compatible_candidate_observed"])
        self.assertFalse(r["physical_region_verified"])
        self.assertTrue(a.verify_report(r)["platform_device_name_seen"])

    def test_probe_all_no_can_still_have_pstore(self):
        r = p.parse(SAMPLE.replace("__UMI_P1I_PLATFORM_RAMOOPS__\nyes",
                                   "__UMI_P1I_PLATFORM_RAMOOPS__\nno"))
        self.assertFalse(r["ramoops_platform_device_name_observed"])
        self.assertTrue(r["pstore_mounted"])
        self.assertFalse(r["ramoops_backend_mapping_verified"])

    def test_probe_reject_other_device(self):
        with self.assertRaisesRegex(ValueError, "not umi"):
            p.parse(SAMPLE.replace("\numi\n", "\nelish\n", 1))

    def test_probe_reject_a_b(self):
        with self.assertRaisesRegex(ValueError, "A/B"):
            p.parse(SAMPLE.replace("__UMI_P1I_AB_UPDATE__\nfalse",
                                   "__UMI_P1I_AB_UPDATE__\ntrue"))

    def test_probe_report_whitelist(self):
        r = p.parse(SAMPLE)
        r["imei"] = "non-permitted"
        with self.assertRaisesRegex(ValueError, "whitelist"):
            a.verify_report(r)

    def test_probe_report_does_not_verify_ram(self):
        r = p.parse(SAMPLE)
        r["physical_region_verified"] = True
        with self.assertRaisesRegex(ValueError, "unsafe claim"):
            a.verify_report(r)

    def test_script_only_observes_metadata(self):
        s = p.SCRIPT
        for expected in ("ro.product.device", "/proc/mounts",
                         "/sys/bus/platform/devices/ramoops",
                         "/sys/firmware/devicetree/base/reserved-memory",
                         "/sys/module/ramoops/parameters"):
            self.assertIn(expected, s)
        for forbidden in ("dd ", " su ", "reboot ", "fastboot ", "/dev/block/",
                          "/proc/cmdline", "console-ramoops", "pmsg-ramoops",
                          " > /sys/", " > /dev/", "reg |", "dmesg"):
            self.assertNotIn(forbidden, s)

if __name__ == "__main__":
    unittest.main()
