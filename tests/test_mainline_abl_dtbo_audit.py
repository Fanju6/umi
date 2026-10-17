"""Offline umi selected DTBO 11 / ABL base FDT compatibility audit tests."""
import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("p1p", ROOT / "scripts/mainline_abl_dtbo_audit.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def synthetic_fdt(model=b"synthetic"):
    payload = bytearray(64)
    payload.extend(model)
    struct.pack_into(">II", payload, 0, m.MAGIC_FDT, len(payload))
    return bytes(payload)


def synthetic_dtbo():
    entries = [synthetic_fdt(m.EXPECTED_UMI_MODEL if i == 11 else b"board")
               for i in range(12)]
    offset = 32 + 12 * 32
    body = bytearray()
    table = bytearray(12 * 32)
    for i, payload in enumerate(entries):
        struct.pack_into(">8I", table, i * 32,
                         len(payload), offset + len(body), 0, 0, 0, 0, 0, 0)
        body.extend(payload)
    header = struct.pack(">8I", m.MAGIC_DTBO, offset + len(body),
                         32, 32, 12, 32, 4096, 0)
    return header + table + body


class ABLDTBOTests(unittest.TestCase):
    def test_umi_index_11_is_validated(self):
        entries, report = m.parse_dtbo(synthetic_dtbo())
        self.assertEqual(report["selected_index"], 11)
        self.assertEqual(len(entries), 12)
        self.assertTrue(report["umi_model_matched"])

    def test_padded_dtbo_partition_accepted(self):
        raw = synthetic_dtbo()
        _, info = m.parse_dtbo(raw + bytes(4096))
        self.assertEqual(info["downloaded_partition_bytes"], len(raw) + 4096)
        self.assertEqual(info["trailing_padding_bytes"], 4096)
        self.assertEqual(info["selected_index"], 11)

    def test_nonuniform_trailing_partition_bytes_ignored(self):
        raw = synthetic_dtbo()
        _, info = m.parse_dtbo(raw + b"TRAILING-IGNORED")
        self.assertEqual(info["trailing_padding_bytes"], len(b"TRAILING-IGNORED"))
        self.assertEqual(info["trailing_nonzero_bytes_not_parsed"],
                         len(b"TRAILING-IGNORED"))

    def test_wrong_board_model_rejected(self):
        blob = bytearray(synthetic_dtbo())
        start = blob.find(m.EXPECTED_UMI_MODEL)
        self.assertGreater(start, 0)
        blob[start:start + len(m.EXPECTED_UMI_MODEL)] = b"Z" * len(m.EXPECTED_UMI_MODEL)
        with self.assertRaisesRegex(ValueError, "umi model"):
            m.parse_dtbo(blob)

    def test_incorrect_table_size_rejected(self):
        blob = bytearray(synthetic_dtbo())
        struct.pack_into(">I", blob, 16, 9)
        with self.assertRaisesRegex(ValueError, "12-entry"):
            m.parse_dtbo(blob)

    def test_first_vendor_base_fdt_scan(self):
        image = synthetic_fdt(b"First")
        self.assertEqual(m.find_dtb_segments(image), [image])

    def test_concatenated_fdt_scanned(self):
        first = synthetic_fdt(b"1")
        second = synthetic_fdt(b"2")
        buf = first + b"\0" * ((-len(first)) % 4) + second
        parts = m.find_dtb_segments(buf)
        self.assertEqual(parts, [first, second])

    def test_invalid_dtb_magic_rejected(self):
        with self.assertRaises(ValueError):
            m.find_dtb_segments(b"NOT-FDT" * 12)

    def test_no_device_writes(self):
        text = (ROOT / "scripts/mainline_abl_dtbo_audit.py").read_text()
        workflow = (ROOT / ".github/workflows/mainline-abl-dtbo-audit.yml").read_text()
        for banned in ("fastboot flash", "adb shell", "dd if=/dev/block",
                       "avbtool add_hash_footer", "sysrq-trigger"):
            self.assertNotIn(banned, text)
            self.assertNotIn(banned, workflow)

    def test_compatibility_shim_only_adds_abl_symbols(self):
        text = (ROOT / "research/mainline/sm8250-xiaomi-umi-p1q.dts").read_text()
        self.assertIn('#include "sm8250-xiaomi-umi-p1n.dts"', text)
        self.assertIn("arch_timer: timer", text)
        self.assertIn("qcom_tzlog: tz-log@146bf720", text)
        self.assertIn('status = "disabled";', text)
        self.assertNotIn("interrupts =", text)
        self.assertNotIn('status = "okay"', text)

    def test_p1n_p1q_can_be_compared_without_flashing(self):
        text = (ROOT / ".github/workflows/mainline-abl-dtbo-audit.yml").read_text()
        self.assertIn("--compatibility-dtb input/umi-p1q.dtb", text)
        self.assertIn("fdtget -t s input/umi-p1q.dtb /__symbols__ arch_timer", text)
        self.assertIn("fdtget -t x input/umi-p1q.dtb /timer interrupts", text)
        self.assertNotIn("fastboot flash", text)

    def test_original_and_mainline_separate(self):
        source = (ROOT / "scripts/mainline_abl_dtbo_audit.py").read_text()
        self.assertIn('"mainline_p1n"', source)
        self.assertIn('f"official_base_{i}"', source)
        self.assertIn('"safe_to_flash": False', source)

if __name__ == "__main__":
    unittest.main()
