"""P1c RPMh regulator topology research-only validation."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("p1c", ROOT / "scripts/mainline_p1c_topology.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class P1cTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(m.MATRIX.read_text())
        self.p1b = json.loads(m.P1B.read_text())
        self.live = json.loads(m.LIVE.read_text())
        self.dts = m.DTS.read_text()

    def run_check(self):
        return m.check(self.manifest, self.dts, self.p1b, self.live)

    def test_seven_outputs_six_parent_groups_and_eight_consumers(self):
        r = self.run_check()
        self.assertEqual(r["PM8150_outputs_modeled"], 7)
        self.assertEqual(r["distinct_parent_property_groups"], 6)
        self.assertEqual(r["legacy_supply_edges_accounted"], 8)
        self.assertEqual(r["provider_status"], "disabled")
        self.assertFalse(r["safe_to_flash"])

    def test_inputs_are_explicitly_unknown(self):
        for rail in self.manifest["outputs"]:
            self.assertIsNone(rail["parent_phandle"])
            self.assertIsNone(rail["mainline_voltage_range"])

    def test_refuse_power_supply_guess(self):
        self.manifest["outputs"][0]["parent_phandle"] = "vph_pwr"
        with self.assertRaisesRegex(ValueError, "unverified power graph"):
            self.run_check()

    def test_refuse_copying_old_rail_max_to_mainline(self):
        self.dts = self.dts.replace("umi_p1c_l17: ldo17 {};",
                                    "umi_p1c_l17: ldo17 { regulator-max-microvolt = <3008000>; };")
        with self.assertRaisesRegex(ValueError, "unexpected live"):
            self.run_check()

    def test_provider_must_stay_disabled(self):
        self.dts = self.dts.replace('status = "disabled";', 'status = "okay";')
        with self.assertRaisesRegex(ValueError, "disabled"):
            self.run_check()

    def test_reject_unknown_pmic_id_claim(self):
        self.manifest["provider"]["pmic_id_verified_on_umi"] = True
        with self.assertRaisesRegex(ValueError, "forbids"):
            self.run_check()

    def test_reject_modified_rail_parent_property(self):
        self.manifest["outputs"][0]["parent_supply_property"] = "vdd-s9-supply"
        with self.assertRaisesRegex(ValueError, "parent group mismatch"):
            self.run_check()

    def test_reject_missing_upstream_consumers(self):
        self.p1b["rails"].pop()
        with self.assertRaisesRegex(ValueError, "eight"):
            self.run_check()

    def test_reject_wrong_voltage_snapshot(self):
        self.manifest["outputs"][0]["legacy_observed_microvolts"] = 2200000
        with self.assertRaisesRegex(ValueError, "measurement drift"):
            self.run_check()

    def test_reject_missing_reference_board_or_binding(self):
        with self.assertRaisesRegex(ValueError, "apps_rsc"):
            m.check_sources("bad", "", "bad")

    def test_do_not_expose_regulator_rails_via_new_phandles(self):
        s = self.dts
        self.assertNotIn("<&umi_p1c_", s)
        self.assertNotIn("vcc-supply", s)
        self.assertNotIn("regulator-min-microvolt", s)
