"""Validate the anonymized P1b live PM8150 rails without treating them as GKI voltages."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "p1b_evidence", ROOT / "scripts/mainline_p1b_observations.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class P1bObservationTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads(mod.OBSERVED.read_text())
        self.mapping = json.loads(mod.MATRIX.read_text())

    def test_eight_links_and_seven_rails_accounted(self):
        result = mod.verify(self.snapshot, self.mapping)
        self.assertEqual(result["legacy_supplies_observed"], 7)
        self.assertEqual(result["legacy_dts_links_accounted"], 8)
        self.assertFalse(result["voltage_is_safe_for_mainline"])

    def test_l17_snapshot_is_not_fixed_to_max_limit(self):
        l17 = next(x for x in self.snapshot["rails"] if x["name"] == "pm8150_l17")
        self.assertEqual(l17["observed_microvolts"], 2504000)
        self.assertEqual(l17["reported_max_microvolts"], 3008000)
        self.assertFalse(self.snapshot["safety"]["safe_board_voltage_ranges_verified"])

    def test_reject_unknown_extra_physical_regulator(self):
        item = json.loads(json.dumps(self.snapshot))
        item["rails"][0]["name"] = "pm8150_l5_ao"
        with self.assertRaisesRegex(ValueError, "unexpected"):
            mod.verify(item, self.mapping)

    def test_reject_voltage_outside_reported_limits(self):
        item = json.loads(json.dumps(self.snapshot))
        item["rails"][0]["observed_microvolts"] = 9999999
        with self.assertRaisesRegex(ValueError, "impossible"):
            mod.verify(item, self.mapping)

    def test_reject_voltage_config_approval(self):
        item = json.loads(json.dumps(self.snapshot))
        item["safety"]["safe_board_voltage_ranges_verified"] = True
        with self.assertRaisesRegex(ValueError, "not allowed"):
            mod.verify(item, self.mapping)

    def test_reject_lost_ufs_phy_rail_link(self):
        item = json.loads(json.dumps(self.mapping))
        item["rails"].pop()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            mod.verify(self.snapshot, item)

    def test_can_compare_without_publishing_original_user_report(self):
        report = {"schema_version": 1, "phase": "P1b", "device": "umi",
                  "safe_to_flash": False, "writes_performed": False,
                  "groups": {"regulator": {}, "typec": {"port0": {
                      "data_role": "host [device]", "power_role": "source [sink]"}},
                      "usb_supply": {"usb": {"type": "USB_PD", "online": "1"}}},
                  "summary": {"regulator": 56}}
        for rail in self.snapshot["rails"]:
            report["groups"]["regulator"][rail["name"]] = {
                "name": rail["name"], "microvolts": str(rail["observed_microvolts"]),
                "min_microvolts": str(rail["reported_min_microvolts"]),
                "max_microvolts": str(rail["reported_max_microvolts"]),
                "state": "enabled"}
        for i in range(49):
            report["groups"]["regulator"][f"extra{i}"] = {
                "name": f"not-ufs{i}", "state": "disabled"}
        self.assertTrue(mod.compare_with_uncommitted_report(report, self.snapshot))
        report["groups"]["regulator"]["pm8150_l5"]["microvolts"] = "900000"
        with self.assertRaisesRegex(ValueError, "value changed"):
            mod.compare_with_uncommitted_report(report, self.snapshot)
