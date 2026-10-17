"""P0b observed DT vs pinned upstream 6.12 reserved-memory contract."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("memcompare", ROOT / "scripts/mainline_compare_memory.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class MainlineMemoryCompareTests(unittest.TestCase):
    def setUp(self):
        self.baseline = json.loads(mod.BASELINE.read_text(encoding="utf-8"))
        self.fixture = {
            "device": "umi", "phase": "P0b-reg", "address_cells": 2, "size_cells": 2,
            "safe_to_flash": False, "memory_contents_read": False,
            "regions": {
                "hyp_region@80000000": {"status": "observed", "ranges": [
                    {"base": "0x80000000", "size": "0x600000", "bytes": 0x600000}]},
                "xbl_aop_region@80700000": {"status": "observed", "ranges": [
                    {"base": "0x80600000", "size": "0x260000", "bytes": 0x260000}]},
                "disp_rdump_region@9c000000": {"status": "observed", "ranges": [
                    {"base": "0xb0400000", "size": "0x1000000", "bytes": 0x1000000}]},
            },
        }

    def test_baseline_is_locked_and_nonflashable(self):
        mod.validate(self.baseline, self.fixture)
        self.assertFalse(self.baseline["safety"]["safe_to_flash"])
        self.assertEqual(len(self.baseline["regions"]), 18)

    def test_detects_live_xbl_reg_overrides_misleading_node_name(self):
        r = mod.compare(self.baseline, self.fixture)
        by_name = {x["name"]: x for x in r["comparison"]}
        self.assertEqual(by_name["xbl_aop_mem"]["state"], "different")
        self.assertEqual(by_name["xbl_aop_mem"]["live_ranges"][0]["base"], "0x80600000")
        self.assertEqual(r["live_internal_overlaps"], [])
        self.assertFalse(r["linux_612_boot_verified"])

    def test_rejects_invalid_user_report(self):
        item = dict(self.fixture)
        item["device"] = "dagu"
        with self.assertRaises(ValueError):
            mod.compare(self.baseline, item)

    def test_detects_true_overlap(self):
        other = json.loads(json.dumps(self.fixture))
        other["regions"]["hyp_region@80000000"]["ranges"][0]["size"] = "0x700000"
        other["regions"]["hyp_region@80000000"]["ranges"][0]["bytes"] = 0x700000
        r = mod.compare(self.baseline, other)
        self.assertEqual(len(r["live_internal_overlaps"]), 1)

    def test_adjacency_is_not_overlap(self):
        self.assertFalse(mod.overlapping([
            {"node": "a", "base": 0, "end": 0x10},
            {"node": "b", "base": 0x10, "end": 0x20},
        ]))

    def test_unreadable_nodes_not_treated_as_missing(self):
        item = json.loads(json.dumps(self.fixture))
        item["regions"]["hyp_region@80000000"] = {"status": "unreadable"}
        result = mod.compare(self.baseline, item)
        hyp = next(x for x in result["comparison"] if x["name"] == "hyp_mem")
        self.assertEqual(hyp["state"], "unmapped_or_unread")

    def test_blocks_bad_byte_counts(self):
        self.fixture["regions"]["hyp_region@80000000"]["ranges"][0]["bytes"] = 12
        with self.assertRaisesRegex(ValueError, "bytes"):
            mod.compare(self.baseline, self.fixture)

    def test_rejects_bad_baseline_commit(self):
        other = json.loads(json.dumps(self.baseline))
        other["source"]["commit"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "未审核"):
            mod.compare(other, self.fixture)
