"""Test experimental umi console-only ramoops DTS remains isolated and safe."""
import json
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DTS=ROOT/"research/mainline/sm8250-xiaomi-umi-p1n.dts"
PREFLIGHT=ROOT/"config/mainline-umi-preflight-observed.json"

class ExperimentalRAMConsoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dts=DTS.read_text(encoding="utf-8")
        cls.p=json.loads(PREFLIGHT.read_text(encoding="utf-8"))

    def test_inherits_disabled_p1m(self):
        self.assertIn('#include "sm8250-xiaomi-umi-p1m.dts"',self.dts)

    def test_ramoops_matches_real_physical_range(self):
        self.assertEqual(self.p["pstore"]["memory_base"],"0xb0000000")
        self.assertEqual(self.p["pstore"]["memory_size_bytes"],0x400000)
        self.assertIn('reg = <0x0 0xb0000000 0x0 0x400000>;',self.dts)
        self.assertEqual(self.p["pstore"]["console_size_bytes"],0x200000)
        self.assertEqual(self.p["pstore"]["pmsg_size_bytes"],0x200000)

    def test_console_and_pmsg_not_record_ring(self):
        self.assertIn('console-size = <0x200000>;',self.dts)
        self.assertIn('pmsg-size = <0x200000>;',self.dts)
        self.assertIn('record-size = <0x0>;',self.dts)
        self.assertEqual(self.p["pstore"]["record_size_bytes"],0)

    def test_but_no_claim_of_surviving_twrp(self):
        self.assertFalse(self.p["pstore"]["linux_612_early_boot_crash_capture_verified"])
        self.assertIn("NOT been proved",self.dts)

    def test_six_hardware_blocks_disabled(self):
        for node in ("ufs_mem_hc","ufs_mem_phy","usb_1","usb_1_dwc3","usb_1_hsphy","usb_1_qmpphy"):
            self.assertRegex(self.dts,r"&"+node+r'\s*\{\s*status\s*=\s*"disabled";\s*\};')

    def test_no_parent_or_voltage_guesses(self):
        for forbidden in ("regulator-min-microvolt", "regulator-max-microvolt",
                          "vdd-l6-l9-supply","vdd-l13-l16-l17-supply"):
            self.assertNotIn(forbidden,self.dts)

if __name__=="__main__":
    unittest.main()
