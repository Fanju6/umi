"""P1f UFS extra-regulator behavior and safety regression; no device access."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("p1f", ROOT / "scripts/mainline_p1f_ufs_lifecycle.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class P1fTests(unittest.TestCase):
    def setUp(self):
        self.g = json.loads(m.GRAPH.read_text(encoding="utf-8"))
        self.p1e = json.loads(m.P1E.read_text(encoding="utf-8"))

    def check(self):
        return m.validate(self.g, self.p1e)

    def test_baseline(self):
        r = self.check()
        self.assertEqual(r["vendor_vote_paths"], 2)
        self.assertEqual(r["unknown_parent_groups"], 6)
        self.assertFalse(r["safe_to_flash"])

    def test_vddp_enable_vs_hibern8_load(self):
        self.assertEqual(self.g["votes"][0]["init"], "enable")
        self.assertEqual(self.g["votes"][0]["link_off"], "disable")
        self.assertEqual(self.g["votes"][0]["hibern8"], "set_min_load")

    def test_vccq_parent_load_not_enable(self):
        self.assertEqual(self.g["votes"][1]["init"], "set_load")
        self.assertEqual(self.g["votes"][1]["max_uA_in_vendor_dts"], 210000)
        self.assertFalse(self.g["interpretation"]["vccq_parent_direct_enable"])

    def test_reject_assumed_vph_voltage(self):
        self.g["interpretation"]["fixed_vph_voltage_uv"] = 3700000
        with self.assertRaisesRegex(ValueError, "power conclusion"):
            self.check()

    def test_reject_fake_mainline_equivalence(self):
        self.g["votes"][0]["mainline_replacement"] = "ref_clk"
        with self.assertRaisesRegex(ValueError, "replacement"):
            self.check()

    def test_reject_parent_as_vccq_supply(self):
        self.g["votes"][1]["mainline_replacement"] = "vccq-supply"
        with self.assertRaisesRegex(ValueError, "replacement"):
            self.check()

    def test_reject_direct_enable_instead_of_load(self):
        self.g["votes"][1]["init"] = "enable"
        with self.assertRaisesRegex(ValueError, "lifecycle drift"):
            self.check()

    def test_reject_unproven_wiring(self):
        self.g["interpretation"]["board_wiring_proven"] = True
        with self.assertRaisesRegex(ValueError, "power conclusion"):
            self.check()

    def test_reject_missing_wlan_s8c_consumer(self):
        self.g["shared_s8c_references"].pop()
        with self.assertRaisesRegex(ValueError, "shared S8C"):
            self.check()

    def test_reject_unsafe_flash(self):
        self.g["boundaries"]["safe_to_flash"] = True
        with self.assertRaisesRegex(ValueError, "unsafe research"):
            self.check()

    def test_reject_changed_legacy_max_current(self):
        self.g["votes"][0]["max_uA_in_vendor_dts"] = 2500
        with self.assertRaisesRegex(ValueError, "lifecycle drift"):
            self.check()

    def test_reject_partial_source_set(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            m.verify_sources(self.g, {"legacy_ufs": ""})

    def test_missing_c_function_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "missing function"):
            m.c_function("", "ufs_qcom_init")

if __name__ == "__main__":
    unittest.main()
