"""Synthetic Android DTBO v0 and FDT structure regression, no phone needed."""
import importlib.util
import json
import struct
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "inspect_dtbo", ROOT / "scripts/mainline_dtbo_offline_inspect.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def align(raw):
    return raw + b"\0" * ((-len(raw)) % 4)

def fdt(*, name="qcom,umi", supply="qcom,vccq-parent-supply"):
    strings = b"compatible\0model\0target-path\0" + supply.encode() + b"\0"
    off_compat, off_model = 0, len(b"compatible\0")
    off_target = len(b"compatible\0model\0")
    off_supply = len(b"compatible\0model\0target-path\0")
    chunks = []
    def begin(name):
        chunks.append(struct.pack(">I", 1) + align(name.encode() + b"\0"))
    def end():
        chunks.append(struct.pack(">I", 2))
    def prop(offset, payload):
        chunks.append(struct.pack(">3I", 3, len(payload), offset) + align(payload))
    begin("")
    prop(off_compat, name.encode() + b"\0")
    prop(off_model, b"Xiaomi umi\0")
    begin("fragment@0")
    prop(off_target, b"/soc/ufs@1d84000\0")
    begin("__overlay__")
    prop(off_supply, struct.pack(">I", 10))
    end()
    end()
    end()
    chunks.append(struct.pack(">I", 9))
    structure = b"".join(chunks)
    strings_at = 56 + len(structure)
    total = strings_at + len(strings)
    header = struct.pack(">10I", 0xd00dfeed, total, 56, strings_at,
                         40, 17, 16, 0, len(strings), len(structure))
    return header + bytes(16) + structure + strings

def dtbo(n=2):
    overlays = [fdt(name="qcom,umi%d" % i) for i in range(n)]
    pos = 32 + n * 32
    entries = []
    for i, item in enumerate(overlays):
        entries.append(struct.pack(">8I", len(item), pos, 0x42 + i, 1,
                                   0, 0, 0, 0))
        pos += len(item)
    header = struct.pack(">8I", 0xd7b7ab1e, pos, 32, 32, n, 32, 4096, 0)
    return header + b"".join(entries) + b"".join(overlays)

class DTBOInspectTests(unittest.TestCase):
    def test_valid_two_entries_and_fdt_subset(self):
        data = m.inspect_image(dtbo(2), expected_count=2)
        self.assertEqual(data["dtbo_entry_count"], 2)
        self.assertEqual(data["entries"][1]["root_compatible"], ["qcom,umi1"])
        self.assertIn("/soc/ufs@1d84000",
                      data["entries"][0]["fragment_target_paths"])
        self.assertEqual(data["entries"][0]["power_property_locations"][0]["property"],
                         "qcom,vccq-parent-supply")
        self.assertFalse(data["safe_to_flash"])
        self.assertFalse(data["bootloader_overlay_choice_verified"])

    def test_twelve_entries(self):
        data = m.inspect_image(dtbo(12), expected_count=12)
        self.assertEqual(len(data["entries"]), 12)
        self.assertTrue(all(x["fdt_structurally_parsed"] for x in data["entries"]))

    def test_distinct_ids_not_selection_claim(self):
        data = m.inspect_image(dtbo(2))
        self.assertEqual(data["entries"][0]["id_hex"], "0x00000042")
        self.assertFalse(data["runtime_merged_dt_verified_by_this_probe"])

    def test_no_fdt_property_values_exposed(self):
        out = json.dumps(m.inspect_image(dtbo(2)))
        self.assertNotIn("0x0000000a", out)
        self.assertNotIn("dtb_binary", out)

    def test_declared_size_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "declared size"):
            m.inspect_image(dtbo(2), expected_total=5514578)

    def test_declared_count_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "entry count differs"):
            m.inspect_image(dtbo(2), expected_count=12)

    def test_truncated_image_fails(self):
        with self.assertRaisesRegex(ValueError, "bounds"):
            m.inspect_image(dtbo(2)[:90])

    def test_bad_magic_rejected(self):
        data = bytearray(dtbo())
        data[0] = 0
        with self.assertRaisesRegex(ValueError, "DTBO v0"):
            m.inspect_image(bytes(data))

    def test_bad_entry_offset_rejected(self):
        data = bytearray(dtbo(2))
        struct.pack_into(">I", data, 36, 5)
        with self.assertRaisesRegex(ValueError, "range invalid"):
            m.inspect_image(bytes(data))

    def test_bad_fdt_header_rejected(self):
        data = bytearray(dtbo(2))
        data[96:100] = b"ABCD"
        with self.assertRaisesRegex(ValueError, "FDT header"):
            m.inspect_image(bytes(data))

    def test_unexpected_fdt_property_not_leaked(self):
        out = json.dumps(m.inspect_image(dtbo(2)))
        self.assertNotIn("private_password", out)

    def test_requires_root_explicit_device_preflight(self):
        calls = []
        def fake_run(args, **kw):
            calls.append(args)
            return m.subprocess.CompletedProcess(args, 0, b"dada\n", b"")
        with mock.patch.object(m.subprocess, "run", side_effect=fake_run):
            with self.assertRaisesRegex(ValueError, "not umi"):
                m.collect("adb")
        self.assertEqual(len(calls), 1)

    def test_device_shell_only_read(self):
        import inspect
        source = inspect.getsource(m.collect)
        self.assertIn('dd if=', source)
        self.assertNotIn("dd of=", source)
        self.assertNotIn("fastboot", source)
        self.assertNotIn("reboot", source)
        self.assertNotIn("mount -t", source)

if __name__ == "__main__":
    unittest.main()
