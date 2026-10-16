"""Regression gates for umi P0c whitelist collector and research-only DTS."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S = importlib.util.spec_from_file_location("memprobe34", ROOT / "scripts/mainline_full_reserved_probe.py")
M = importlib.util.module_from_spec(S)
S.loader.exec_module(M)


def record(raw="missing"):
    entries = {"ID": "umi", "AC": "00 00 00 02", "SC": "00 00 00 02"}
    for name in M.NODES:
        entries[name + "|exists"] = "1"
        for p in M.PROPS:
            entries[name + "|" + p] = raw
        for p in M.FLAGS:
            entries[name + "|" + p] = "0"
    return entries


def wire(values):
    return "\n".join(M.TAG + " " + k + " " + v for k, v in values.items()) + "\n" + M.END + "\n"


class MainlineP0cTests(unittest.TestCase):
    def test_whitelist_exactly_34_nodes(self):
        self.assertEqual(len(M.NODES), 34)
        self.assertEqual(len(set(M.NODES)), 34)
        self.assertIn("linux,cma", M.NODES)

    def test_missing_reg_is_not_missing_hardware(self):
        result = M.parse(wire(record()))
        self.assertEqual(result["regions"]["linux,cma"]["reg"]["status"], "missing")
        self.assertEqual(result["summary"]["fixed_reg_ranges"], 0)
        self.assertFalse(result["safe_to_flash"])

    def test_decode_dynamic_cma_size(self):
        vals = record()
        vals["linux,cma|size"] = "00 00 00 00 04 00 00 00"
        vals["linux,cma|reusable"] = "1"
        out = M.parse(wire(vals))["regions"]["linux,cma"]
        self.assertEqual(out["size"]["value"], "0x4000000")
        self.assertTrue(out["reusable"])

    def test_reject_other_device_and_partial_data(self):
        bad = record()
        bad["ID"] = "elish"
        with self.assertRaises(ValueError):
            M.parse(wire(bad))
        bad["ID"] = "umi"
        with self.assertRaises(ValueError):
            M.parse(wire(bad).replace(M.END, ""))

    def test_detect_overlap_between_static_ranges(self):
        v = record()
        a = "00 00 00 00 80 00 00 00 00 00 00 00 00 60 00 00"
        b = "00 00 00 00 80 50 00 00 00 00 00 00 00 20 00 00"
        v["hyp_region@80000000|reg"] = a
        v["xbl_aop_region@80700000|reg"] = b
        result = M.parse(wire(v))
        self.assertEqual(len(result["summary"]["overlaps_for_manual_review"]), 1)

    def test_read_only_whitelist_shell_commands(self):
        s = M.commands()
        self.assertNotIn("su -c", s)
        for forbidden in ("dd if=", "/proc/kcore", "/dev/mem", "setprop ", "fastboot ", "chmod ", "getprop |"):
            self.assertNotIn(forbidden, s)
        self.assertIn("|reg ", s)  # check the planned read-only property commands

    def test_dts_never_claims_boot_ready(self):
        dts = (ROOT / "research/mainline/sm8250-xiaomi-umi-p0c.dts").read_text()
        self.assertIn("OFFLINE-ONLY", dts)
        self.assertNotIn('status = "okay"', dts)
        self.assertNotIn("qcom,board-id", dts)
        for label in ("xbl_aop_mem", "slpi_mem", "adsp_mem", "spss_mem", "cdsp_secure_heap"):
            self.assertIn("/delete-node/ &" + label + ";", dts)
        for addr, size in (("80600000", "260000"), ("88c00000", "2f00000"),
                           ("8bb00000", "2500000"), ("8e000000", "100000"),
                           ("8e100000", "4600000")):
            self.assertIn("0x" + addr + " 0x0 0x" + size, dts)
