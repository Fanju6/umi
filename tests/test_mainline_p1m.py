"""P1m: verify grounded umi runtime phandles became OFFLINE-ONLY 6.12 labels."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "config/mainline-p1m-ufs-runtime-links.json"
DTS = ROOT / "research/mainline/sm8250-xiaomi-umi-p1m.dts"
P1C = ROOT / "research/mainline/sm8250-xiaomi-umi-p1c.dts"
P1A = ROOT / "research/mainline/sm8250-xiaomi-umi-p1a.dts"
EXPECTED = {
    ("ufs_mem_phy", "vdda-phy-supply"): ("pm8150_l5", "umi_p1c_l5"),
    ("ufs_mem_phy", "vdda-pll-supply"): ("pm8150_l9", "umi_p1c_l9"),
    ("ufs_mem_hc", "vcc-supply"): ("pm8150_l17", "umi_p1c_l17"),
    ("ufs_mem_hc", "vccq-supply"): ("pm8150_l6", "umi_p1c_l6"),
    ("ufs_mem_hc", "vccq2-supply"): ("pm8150_s4", "umi_p1c_s4"),
}
VOTES = {"qcom,vddp-ref-clk-supply", "qcom,vccq-parent-supply"}

class P1mTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = json.loads(GRAPH.read_text(encoding="utf-8"))
        cls.dts = DTS.read_text(encoding="utf-8")
        cls.p1c = P1C.read_text(encoding="utf-8")
        cls.p1a = P1A.read_text(encoding="utf-8")

    def test_device_identity(self):
        self.assertEqual(self.graph["device"], "umi")
        self.assertEqual(self.graph["root_runtime"]["board_id"], [43, 0])
        self.assertEqual(self.graph["root_runtime"]["model"],
                         "Qualcomm Technologies, Inc. xiaomi umi")
        self.assertEqual(self.graph["stage"], "P1m")

    def test_eight_links_and_known_five_standard_supplies(self):
        links = self.graph["runtime_links"]
        self.assertEqual(len(links), 8)
        self.assertEqual(len({(x["consumer"], x["property"]) for x in links}), 8)
        standard = {(x["consumer"], x["property"]):
                    (x["legacy_provider"], x["mainline_research_provider_label"])
                    for x in links if x["mainline_research_provider_label"] is not None}
        self.assertEqual(standard, EXPECTED)
        self.assertTrue(all(x["old_phandle_is_not_reusable_for_mainline"]
                            for x in links))

    def test_live_runtime_gdsc_identity_not_falsely_proven(self):
        d = self.graph["legacy_vdd_hba"]
        self.assertEqual(d["observed_runtime_phandle"], "0x00000076")
        self.assertTrue(d["phandle_found_in_runtime_fdt"])
        self.assertFalse(d["runtime_provider_identity_classified"])
        self.assertEqual(d["vendor_label"], "ufs_phy_gdsc")
        self.assertEqual(d["mainline_612_power_domain"],
                         "<&gcc UFS_PHY_GDSC>")

    def test_private_votes_accounted_but_not_implemented(self):
        links = self.graph["runtime_links"]
        self.assertEqual({x["property"] for x in links
                          if x["kind"] == "vendor_only_vote"}, VOTES)
        self.assertEqual(set(self.graph["mainline_draft"]["vendor_votes_unmapped"]),
                         VOTES)
        self.assertTrue(self.graph["mainline_draft"]["vdd_hba_legacy_regulator_not_copied"])
        for prop in VOTES | {"vdd-hba-supply"}:
            self.assertNotRegex(self.dts, r"(?m)^\s*" + re.escape(prop) + r"\s*=")

    def test_actual_dts_properties_use_labels_not_legacy_numeric_handles(self):
        self.assertIn('#include "sm8250-xiaomi-umi-p1c.dts"', self.dts)
        for (node, prop), (legacy, label) in EXPECTED.items():
            block = re.search(r"&" + node + r"\s*\{([^{}]*)\};", self.dts, re.S)
            self.assertIsNotNone(block, "missing " + node)
            self.assertRegex(block.group(1), re.escape(prop) +
                             r"\s*=\s*<&" + label + r">;")
            self.assertRegex(self.p1c, label + r":\s*(?:ldo[0-9]+|smps[0-9]+)\s*\{")
        self.assertNotRegex(self.dts, r"<0x00000(?:07f|080|2d4|2cf|0ac|0ae)>")

    def test_hardware_remains_disabled(self):
        for node in ("ufs_mem_hc", "ufs_mem_phy"):
            match = re.search(r"&" + node + r"\s*\{([^{}]*)\};", self.dts, re.S)
            self.assertIsNotNone(match)
            self.assertRegex(match.group(1), r'status\s*=\s*"disabled";')
        self.assertRegex(self.p1c, r'regulators-umi-reference\s*\{[^{}]*status\s*=\s*"disabled";')
        for node in ("ufs_mem_hc", "ufs_mem_phy", "usb_1", "usb_1_dwc3",
                     "usb_1_hsphy", "usb_1_qmpphy"):
            self.assertRegex(self.p1a, r"&" + node + r'\s*\{\s*status\s*=\s*"disabled";')

    def test_no_voltage_or_parent_wiring_guessed(self):
        for forbidden in ("regulator-min-microvolt", "regulator-max-microvolt",
                          "regulator-always-on", "regulator-boot-on",
                          "vdd-l6-l9-supply", "vdd-l13-l16-l17-supply"):
            self.assertNotIn(forbidden, self.dts)
        draft = self.graph["mainline_draft"]
        self.assertFalse(draft["pm8150_input_parents_verified"])
        self.assertFalse(draft["regulator_voltages_for_612_verified"])
        self.assertFalse(draft["provider_enabled"])
        self.assertFalse(draft["ufs_enabled"])
        self.assertFalse(draft["usb_enabled"])

    def test_unconditionally_no_flash(self):
        gate = self.graph["safety"]
        self.assertEqual(gate, {
            "safe_to_attempt_mainline_boot": False, "safe_to_flash": False,
            "boot_image_created": False, "mainline_runtime_tested": False
        })

if __name__ == "__main__":
    unittest.main()
