"""Offline safeguards around umi RPMh resource ID inference and UFS extras."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("p1d", ROOT / "scripts/mainline_p1d_rpmh_audit.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class P1dEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.graph = json.loads(m.GRAPH.read_text())
        self.p1c = json.loads(m.P1C.read_text())

    def check(self):
        return m.validate(self.graph, self.p1c)

    def test_seven_resources_and_unverified_mainline_id(self):
        result = self.check()
        self.assertEqual(result["locked_resources"], 7)
        self.assertEqual(result["rpmh_suffix"], "a")
        self.assertFalse(result["mainline_pmic_id_proven"])
        self.assertEqual(result["extra_ufs_vendor_edges"], 2)
        self.assertFalse(result["safe_to_flash"])

    def test_same_l6_l9_parent_property_not_same_rail(self):
        rails = {r["legacy"]: r for r in self.graph["rails"]}
        self.assertEqual(rails["pm8150_l6"]["parent_property"],
                         rails["pm8150_l9"]["parent_property"])
        self.assertNotEqual(rails["pm8150_l6"]["resource"],
                            rails["pm8150_l9"]["resource"])

    def test_cannot_infer_input_from_elish_or_snapshot(self):
        self.graph["rails"][0]["parent_supply_phandle"] = "vph_pwr"
        with self.assertRaisesRegex(ValueError, "unknown supply"):
            self.check()

    def test_reject_verified_boot_or_pm_id(self):
        self.graph["boundaries"]["pmic_id_tested_on_mainline"] = True
        with self.assertRaisesRegex(ValueError, "offline-only"):
            self.check()

    def test_reject_voltage_constraints_inferred_from_419(self):
        self.graph["rails"][2]["mainline_constraint_uv"] = [880000, 880000]
        with self.assertRaisesRegex(ValueError, "unknown supply"):
            self.check()

    def test_two_additional_ufs_dependencies_are_retained(self):
        extras = {x["property"]: x for x in self.graph["extra_ufs_dependencies"]}
        self.assertEqual(extras["qcom,vddp-ref-clk-supply"]["vendor_phandle"], "pm8150_l6")
        self.assertEqual(extras["qcom,vccq-parent-supply"]["vendor_phandle"], "pm8150a_s8")

    def test_reject_missing_vccq_parent_supply(self):
        self.graph["extra_ufs_dependencies"].pop()
        with self.assertRaisesRegex(ValueError, "extra supply"):
            self.check()

    def test_proven_resource_suffix_does_not_enable_rpmh_provider(self):
        self.assertFalse(self.graph["provider_identity"]["safe_to_enable"])
        self.assertTrue(self.graph["boundaries"]["no_enabled_hardware"])

    def test_vendor_filename_and_source_pin(self):
        self.assertIn("arch/arm64/boot/dts/vendor/qcom/kona-regulators.dtsi",
                      self.graph["vendor_files"])
        self.assertEqual(self.graph["locked"]["upstream"], m.PIN_UPSTREAM)

    def test_source_reference_missing_is_hard_failure(self):
        with self.assertRaisesRegex(ValueError, "omits regulator source"):
            m.verify_sources(self.graph, "", "", "", "", "", "")
