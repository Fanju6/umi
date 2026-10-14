import gzip
import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("stock_kernel",ROOT/"scripts/inspect_stock_kernel.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class TestStockKernel(unittest.TestCase):
    def test_embedded_kconfig(self):
        cfg=b"CONFIG_CFI_CLANG=y\n# CONFIG_KSU is not set\nCONFIG_LOCALVERSION=\"-perf\"\n"
        image=b"\x00Linux version 4.19.test\x00"+mod.MARKER_START+gzip.compress(cfg)+mod.MARKER_END
        r=mod.inspect(image,{"CONFIG_CFI_CLANG":"y","CONFIG_KSU":"y","CONFIG_LOCALVERSION":'"-perf"'})
        self.assertTrue(r["ikconfig_found"])
        self.assertEqual(r["stock_critical_config"]["CONFIG_KSU"],"n")
        self.assertEqual(r["config_diff_count"],1)
        self.assertFalse(r["safe_to_flash"])
        self.assertFalse(r["boot_failure_root_cause_proven"])
    def test_missing_config_is_not_misreported_as_match(self):
        r=mod.inspect(b"\x00Linux version 4.19.325\x00")
        self.assertFalse(r["ikconfig_found"])
        self.assertIsNone(r["config_diff_count"])
