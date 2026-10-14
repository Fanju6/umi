"""Non-A/B source and device-profile gate regression tests."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("umi_profile", ROOT / "scripts/check_umi_preflight.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PROFILE = json.loads((ROOT / "config/umi_preflight_20261014.json").read_text(encoding="utf-8"))
SHA = module.pinned_kernel_sha(ROOT / "config/upstream.env")


class UmiPreflightTests(unittest.TestCase):
    def test_known_device_profile_matches_but_is_never_flash_ready(self):
        result = module.inspect(PROFILE, SHA)
        self.assertTrue(result["device_profile_match"])
        self.assertEqual("legacy_non_ab", result["layout"])
        self.assertFalse(result["safe_to_flash"])

    def test_ab_device_is_refused(self):
        changed = copy.deepcopy(PROFILE)
        changed["ab_update"] = "true"
        changed["boot_slot_suffix"] = "_a"
        changed["partition_names"] = ["boot_a", "boot_b", "dtbo_a", "dtbo_b"]
        result = module.inspect(changed, SHA)
        self.assertFalse(result["device_profile_match"])
        self.assertEqual("unconfirmed", result["layout"])

    def test_mismatched_kernel_or_device_rejected(self):
        changed = copy.deepcopy(PROFILE)
        changed["kernel_release"] = "4.19.325-test-other-source"
        self.assertFalse(module.inspect(changed, SHA)["device_profile_match"])
        changed = copy.deepcopy(PROFILE)
        changed["device"] = "cmi"
        self.assertFalse(module.inspect(changed, SHA)["device_profile_match"])

    def test_enforcing_and_dedicated_recovery_are_required(self):
        changed = copy.deepcopy(PROFILE)
        changed["selinux"] = "Permissive"
        self.assertFalse(module.inspect(changed, SHA)["device_profile_match"])
        changed = copy.deepcopy(PROFILE)
        changed["partition_names"].remove("recovery")
        self.assertFalse(module.inspect(changed, SHA)["device_profile_match"])

    def test_no_private_identifiers_in_fixture(self):
        raw = json.dumps(PROFILE, ensure_ascii=False)
        for key in ("serial", "imei", "android_id", "fingerprint", "imei2"):
            self.assertNotIn(key, raw.lower())


if __name__ == "__main__":
    unittest.main()
