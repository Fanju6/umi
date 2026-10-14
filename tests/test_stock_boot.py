"""Synthetic boot header tests. No device writes, no real ROM downloaded."""
import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("boot_audit", ROOT / "scripts/inspect_stock_boot.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def make_image(path: Path, *, version=2, page=4096, kernel=b"K" * 8192,
               ramdisk=b"R" * 4096, dtb=b"D" * 260):
    h = bytearray(page)
    h[:8] = b"ANDROID!"
    for at, n in [(8, len(kernel)), (16, len(ramdisk)),
                   (36, page), (40, version), (44, 0)]:
        struct.pack_into("<I", h, at, n)
    h[48:51] = b"umi"
    if version >= 1:
        struct.pack_into("<I", h, 1644, (mod.HEADER_V1_SIZE, mod.HEADER_V2_SIZE)[version-1])
    if version >= 2:
        struct.pack_into("<I", h, 1648, len(dtb))
    def padded(b):
        return b + b"\0" * (mod.align(len(b), page) - len(b))
    payload = h + padded(kernel) + padded(ramdisk)
    if version >= 2:
        payload += padded(dtb)
    path.write_bytes(payload)


class InspectStockBootTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "boot.img"

    def test_v2_layout_and_hashes(self):
        make_image(self.path)
        r = mod.audit_boot(self.path)
        self.assertEqual(r["boot_header_version"], 2)
        self.assertEqual(r["page_size"], 4096)
        self.assertEqual(r["sections"]["kernel"]["offset"], 4096)
        self.assertEqual(r["sections"]["ramdisk"]["offset"], 4096 + 8192)
        self.assertTrue(r["layout_plausible_for_umi"])
        self.assertFalse(r["safe_to_flash"])
        self.assertEqual(len(r["image_sha256"]), 64)

    def test_wrong_version_still_nonflashable(self):
        make_image(self.path, version=1)
        r = mod.audit_boot(self.path)
        self.assertFalse(r["layout_plausible_for_umi"])
        self.assertFalse(r["safe_to_flash"])

    def test_truncation_refused(self):
        make_image(self.path)
        self.path.write_bytes(self.path.read_bytes()[:4100])
        with self.assertRaises(ValueError):
            mod.audit_boot(self.path)

    def test_nonboot_file_refused(self):
        self.path.write_bytes(b"not a boot image" * 300)
        with self.assertRaises(ValueError):
            mod.audit_boot(self.path)


if __name__ == "__main__":
    unittest.main()
