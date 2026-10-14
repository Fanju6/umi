"""No system writes; smoke tests for boot release gate source."""
import tempfile
import unittest
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("checkboot", ROOT/"scripts/check_experimental_boot.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ExperimentalBootTests(unittest.TestCase):
    def test_gate_fails_closed_in_output(self):
        src=(ROOT/"scripts/check_experimental_boot.py").read_text()
        self.assertIn('"repack_structurally_verified": all(checks.values())',src)
        self.assertIn('"safe_to_flash": False',src)
        self.assertIn('ramdisk_identical_sha256',src)
        self.assertIn('dtb_identical_sha256',src)
    def test_sha256(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"a"
            p.write_bytes(b"abc")
            self.assertEqual(module.checksum(p),"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
