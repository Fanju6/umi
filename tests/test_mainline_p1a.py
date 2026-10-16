"""P1a board-mapping validation; no hardware enabled."""
import importlib.util
import json
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("p1a", ROOT / "scripts/mainline_p1a_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class P1aTests(unittest.TestCase):
    def setUp(self):
        self.m = json.loads(audit.MANIFEST.read_text(encoding="utf-8"))
        self.board = audit.BOARD.read_text(encoding="utf-8")

    def test_verified_p1a_skeleton_has_no_live_nodes(self):
        audit.check_manifest(self.m, self.board)
        self.assertFalse(self.m["safety"]["safe_to_flash"])

    def test_refuse_writing_status_okay(self):
        with self.assertRaisesRegex(ValueError, "enable"):
            audit.check_manifest(self.m, self.board + '\n&ufs_mem_hc { status = "okay"; };\n')

    def test_refuse_early_power_supply_guess(self):
        with self.assertRaisesRegex(ValueError, "invent"):
            audit.check_manifest(self.m, self.board +
                                 "\n&ufs_mem_phy { vdda-phy-supply = <&unknown_rail>; };\n")

    def test_required_mainline_memory_consumers(self):
        self.assertEqual(set(self.m["upstream_memory_consumers"]), audit.CONSUMERS)

    def test_refuse_unreviewed_upstream_version(self):
        m = json.loads(json.dumps(self.m))
        m["upstream"]["sha"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "SHA"):
            audit.check_manifest(m, self.board)

    def test_detect_missing_controller_label_in_source(self):
        m = self.m
        fake = 'ufs_mem_hc: ufshc@1d84000 { reg = <0x01d84000>; };'
        vendors = {x["vendor_file"]: "\n".join(x["vendor_pins"]) for x in m["hardware"]}
        with self.assertRaisesRegex(ValueError, "label missing"):
            audit.check_source(m, fake, vendors)

    def test_manifest_does_not_enable_ufs_or_usb(self):
        self.assertFalse(self.m["safety"]["ufs_enabled"])
        self.assertFalse(self.m["safety"]["usb_enabled"])
        self.assertFalse(self.m["safety"]["regulators_verified"])
