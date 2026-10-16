"""No-device P1e regression and negative safety tests."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("p1e", ROOT / "scripts/mainline_p1e_ufs_audit.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class P1eTests(unittest.TestCase):
    def setUp(self):
        self.g = json.loads(m.GRAPH.read_text(encoding="utf-8"))
        self.old = json.loads(m.P1D.read_text(encoding="utf-8"))
        self.a = m.P1A.read_text(encoding="utf-8")
        self.c = m.P1C.read_text(encoding="utf-8")

    def check(self):
        return m.validate(self.g, self.old, self.a, self.c)

    def test_baseline(self):
        self.assertEqual(self.check()["unknown_parent_groups"], 6)
        self.assertFalse(self.check()["safe_to_flash"])

    def test_vendor_s8_and_bob_resources(self):
        self.assertEqual({x["vrm_resource"] for x in self.g["pm8150a_resources"]},
                         {"smpc8", "bobc1"})
        self.assertEqual({x["pmic_suffix"] for x in self.g["pm8150a_resources"]}, {"c"})

    def test_reject_false_vph_parent(self):
        self.g["parent_inputs"][0]["umi_parent_phandle"] = "vph_pwr"
        with self.assertRaisesRegex(ValueError, "parent phandle"):
            self.check()

    def test_reject_bob_parent_guess(self):
        self.g["parent_inputs"][1]["umi_parent_phandle"] = "pm8150a_bob"
        with self.assertRaisesRegex(ValueError, "parent phandle"):
            self.check()

    def test_reject_ref_clk_as_regulator_vote(self):
        self.g["legacy_ufs_votes"][0]["mainline_equivalent"] = "ref_clk"
        with self.assertRaisesRegex(ValueError, "declared migrated"):
            self.check()

    def test_reject_vccq_as_vendor_parent(self):
        self.g["legacy_ufs_votes"][1]["mainline_equivalent"] = "vccq-supply"
        with self.assertRaisesRegex(ValueError, "declared migrated"):
            self.check()

    def test_reject_wrong_resource(self):
        self.g["pm8150a_resources"][0]["vrm_resource"] = "smpa8"
        with self.assertRaisesRegex(ValueError, "resource mapping"):
            self.check()

    def test_reject_unproven_pm_id(self):
        self.g["pm8150a_resources"][1]["boot_verified"] = True
        with self.assertRaisesRegex(ValueError, "hardware proof"):
            self.check()

    def test_reject_flash_permission(self):
        self.g["safety"]["safe_to_flash"] = True
        with self.assertRaisesRegex(ValueError, "safety gates"):
            self.check()

    def test_reject_vph_as_voltage(self):
        self.g["vph_pwr"]["mainline_voltage_uv"] = 3700000
        with self.assertRaisesRegex(ValueError, "ADC VPH_PWR"):
            self.check()

    def test_reject_p1a_host_enable(self):
        with self.assertRaisesRegex(ValueError, "not disabled"):
            m.verify_dts_safety(self.a.replace('&ufs_mem_hc {\n\tstatus = "disabled";',
                                                 '&ufs_mem_hc {\n\tstatus = "okay";'), self.c)

    def test_reject_p1c_provider_enable(self):
        with self.assertRaisesRegex(ValueError, "provider not disabled"):
            m.verify_dts_safety(self.a, self.c.replace('status = "disabled";', 'status = "okay";'))

    def test_reject_incomplete_source_set(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            m.verify_sources(self.g, {"vendor_vrm": ""})

if __name__ == "__main__":
    unittest.main()
