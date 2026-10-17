"""Unit tests: real umi P0c manifest versus non-bootable DTS draft."""
import importlib.util
import json
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("umi_p0c",ROOT/"scripts/mainline_validate_p0c.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class TestP0cMemory(unittest.TestCase):
    def setUp(self):
        self.data=json.loads(m.MAPPING.read_text())
        self.dts=m.DTS.read_text()
    def test_complete_manifest(self):
        r=m.verify(self.data,self.dts)
        self.assertEqual((r["fixed"],r["dynamic"]),(22,12))
        self.assertFalse(r["safe_to_flash"])
    def test_reject_fixed_overlap(self):
        d=json.loads(json.dumps(self.data))
        d["regions"]["fixed"][1]["base"]="0x80500000"
        with self.assertRaisesRegex(ValueError,"overlapping"):m.verify(d,self.dts)
    def test_reject_wrong_xbl_address(self):
        s=self.dts.replace("0x80600000 0x0 0x260000","0x80700000 0x0 0x160000")
        with self.assertRaisesRegex(ValueError,"incorrect live reg"):m.verify(self.data,s)
    def test_reject_wrong_nomap(self):
        s=self.dts.replace("0x9c000000 0x0 0x2300000>;","0x9c000000 0x0 0x2300000>; no-map;")
        with self.assertRaisesRegex(ValueError,"no-map"):m.verify(self.data,s)
    def test_block_boot_enabled(self):
        with self.assertRaisesRegex(ValueError,"board IDs"):m.verify(self.data,self.dts+"\nqcom,board-id = <0x1 0>;\n")
    def test_dynamic_pool_not_hardcoded(self):
        self.assertNotIn("mailbox-region@",self.dts)
        self.assertEqual(next(x for x in self.data["regions"]["dynamic"] if x["node"]=="secure_display_region")["size"],"0xa400000")
    def test_reject_missing_regions(self):
        d=json.loads(json.dumps(self.data));d["regions"]["dynamic"].pop()
        with self.assertRaisesRegex(ValueError,"incomplete"):m.verify(d,self.dts)
