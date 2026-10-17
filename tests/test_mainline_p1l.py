"""P1l regress schema-allowed versus electrically validated RPMh wiring."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "p1l", ROOT / "scripts/mainline_p1l_regulator_parent_audit.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class P1lTests(unittest.TestCase):
    def setUp(self):
        self.g = json.loads(m.GRAPH.read_text(encoding="utf-8"))
        self.d = json.loads(m.P1D.read_text(encoding="utf-8"))
        self.e = json.loads(m.P1E.read_text(encoding="utf-8"))
        self.f = json.loads(m.P1F.read_text(encoding="utf-8"))
        self.a = m.P1A_DTS.read_text(encoding="utf-8")
        self.c = m.P1C_DTS.read_text(encoding="utf-8")

    def check(self):
        return m.validate(self.g, self.d, self.e, self.f, self.a, self.c)

    def test_baseline(self):
        r = self.check()
        self.assertEqual(r["parent_supply_property_groups"], 6)
        self.assertEqual(r["old_regulator_outputs_grouped"], 7)
        self.assertEqual(r["unmapped_vendor_ufs_votes"], 2)
        self.assertFalse(r["mainline_ufs_regulator_ready"])
        self.assertFalse(r["safe_to_flash"])

    def test_binding_optional_does_not_prove_electrical_connection(self):
        self.assertEqual(self.g["binding"]["required_properties"],
                         ["compatible", "qcom,pmic-id"])
        self.assertFalse(self.g["binding"]["schema_acceptance_proves_wiring"])

    def test_reject_false_required_properties(self):
        self.g["binding"]["required_properties"].append("vdd-l6-l9-supply")
        with self.assertRaisesRegex(ValueError, "binding optional"):
            self.check()

    def test_reject_claim_wiring_from_schema(self):
        self.g["binding"]["schema_acceptance_proves_wiring"] = True
        with self.assertRaisesRegex(ValueError, "binding optional"):
            self.check()

    def test_reject_invented_parent_phandle(self):
        self.g["parent_groups"][0]["umi_parent_phandle"] = "vph_pwr"
        with self.assertRaisesRegex(ValueError, "unsupported umi parent"):
            self.check()

    def test_reject_wrong_group_membership(self):
        self.g["parent_groups"][3]["consumer_ids"] = ["ldo6"]
        with self.assertRaisesRegex(ValueError, "unsupported umi parent"):
            self.check()

    def test_reject_old_reference_changes(self):
        self.d["rails"][0]["parent_property"] = "vdd-l6-l9-supply"
        with self.assertRaisesRegex(ValueError, "contradicts P1l"):
            self.check()

    def test_reject_ufsvote_fake_replacement(self):
        self.g["vendor_only_votes"][0]["mainline_replacement"] = "ref_clk"
        with self.assertRaisesRegex(ValueError, "unsupported legacy vote"):
            self.check()

    def test_reject_voltage_assumption(self):
        self.g["safety"]["voltage_guessed"] = True
        with self.assertRaisesRegex(ValueError, "unsafe P1l"):
            self.check()

    def test_reject_ufs_enable(self):
        self.g["safety"]["mainline_ufs_enabled"] = True
        with self.assertRaisesRegex(ValueError, "unsafe P1l"):
            self.check()

    def test_reject_unsafe_boot_gate(self):
        self.g["safety"]["safe_to_attempt_mainline_boot"] = True
        with self.assertRaisesRegex(ValueError, "unsafe P1l"):
            self.check()

    def test_reject_p1a_dts_hardware_enable(self):
        changed = self.a.replace(
            '&ufs_mem_hc {\n\tstatus = "disabled";\n};',
            '&ufs_mem_hc {\n\tstatus = "okay";\n};')
        if changed == self.a:
            self.skipTest("DTS indentation differs; existing audit still guards")
        with self.assertRaisesRegex(ValueError, "hardware node enabled"):
            m.validate(self.g, self.d, self.e, self.f, changed, self.c)

    def test_reject_provider_enable(self):
        changed = self.c.replace('status = "disabled";', 'status = "okay";', 1)
        with self.assertRaisesRegex(ValueError, "regulator provider no longer disabled"):
            m.validate(self.g, self.d, self.e, self.f, self.a, changed)

    def test_source_crosscheck_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "binding"):
            m.crosscheck_sources("", "")

    def test_mainline_pmic_driver_not_tested(self):
        self.assertFalse(self.g["driver"]["mainline_hardware_probe_verified"])
        self.assertFalse(self.g["confidence"]["mainline_pmic_probed"])

    def test_every_group_has_only_legacy_labels(self):
        target = {r["legacy"] for r in self.d["rails"]}
        actual = {label for g in self.g["parent_groups"]
                  for label in g["legacy_rails"]}
        self.assertEqual(actual, target)


    @staticmethod
    def synthetic_source_pair():
        binding = """properties:
  compatible:
    enum:
      - qcom,pm8150-rpmh-regulators
required:
  - compatible
  - qcom,pmic-id
allOf:
  - if:
      properties:
        compatible:
          enum:
            - qcom,pm8150-rpmh-regulators
            - qcom,pmc8180-rpmh-regulators
    then:
      properties:
        vdd-l2-l10-supply: true
        vdd-l3-l4-l5-l18-supply: true
        vdd-l6-l9-supply: true
        vdd-l7-l12-l14-l15-supply: true
        vdd-l13-l16-l17-supply: true
      patternProperties:
        "^vdd-s([1-9]|10)-supply$": true
  - if:
      properties:
        compatible:
          enum:
            - qcom,other-pmic
    then:
      properties:
        vdd-l999-supply: true
"""
        driver = """vreg->rdesc.supply_name = rpmh_data->supply_name;
vreg->addr = cmd_db_read_addr(rpmh_resource_name);
static const struct rpmh_vreg_init_data pm8150_vreg_data[] = {
"""
        for supply, (_, outputs) in m.GROUPS.items():
            for output in outputs:
                driver += ('    RPMH_VREG("' + output +
                           '", "ldo%s1", &pmic5_nldo, "' +
                           supply.removesuffix("-supply") + '"),\n')
        driver += "};\n"
        return driver, binding

    def test_schema_source_scoped_to_conditional_block(self):
        driver, binding = self.synthetic_source_pair()
        self.assertTrue(m.crosscheck_sources(driver, binding))

    def test_schema_source_rejects_missing_pm8150_property(self):
        driver, binding = self.synthetic_source_pair()
        binding = binding.replace("        vdd-l6-l9-supply: true\n", "")
        with self.assertRaisesRegex(ValueError, "parent property missing"):
            m.crosscheck_sources(driver, binding)

if __name__ == "__main__":
    unittest.main()
