"""Unit tests for the already-booted umi merged-FDT Root parser (no ADB in CI)."""
import importlib.util
import json
import struct
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "merged", ROOT / "scripts/mainline_merged_fdt_ufs_links.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def align(buf):
    return buf + bytes((-len(buf)) % 4)

def sample_fdt(with_model=True):
    names = ("model", "compatible", "qcom,board-id", "serial-number",
             "phandle", "qcom,resource-name", "vcc-supply",
             "qcom,vccq-parent-supply", "vdda-phy-supply", "status")
    offsets = {}
    strings = b""
    for key in names:
        offsets[key] = len(strings)
        strings += key.encode() + b"\0"
    chunks = []
    def begin(name):
        chunks.append(struct.pack(">I", 1) + align(name.encode() + b"\0"))
    def end():
        chunks.append(struct.pack(">I", 2))
    def prop(name, value):
        chunks.append(struct.pack(">3I", 3, len(value), offsets[name]) + align(value))
    begin("")
    if with_model:
        prop("model", b"Qualcomm Technologies, Inc. xiaomi umi\0")
    prop("compatible", b"qcom,kona-mtp\0qcom,kona\0qcom,mtp\0")
    prop("qcom,board-id", struct.pack(">2I", 43, 0))
    begin("chosen")
    prop("serial-number", b"PRIVATE12345\0")
    end()
    begin("soc")
    begin("ufshc@1d84000")
    prop("vcc-supply", struct.pack(">I", 0xA1))
    prop("qcom,vccq-parent-supply", struct.pack(">I", 0xA2))
    end()
    begin("ufsphy@1d87000")
    prop("vdda-phy-supply", struct.pack(">I", 0xA3))
    end()
    end()
    begin("regulators")
    begin("rpmh-regulator-ldoa17")
    prop("phandle", struct.pack(">I", 0xA1))
    prop("qcom,resource-name", b"ldoa17\0")
    end()
    begin("rpmh-regulator-smpc8")
    prop("phandle", struct.pack(">I", 0xA2))
    prop("qcom,resource-name", b"smpc8\0")
    end()
    end()
    end()
    chunks.append(struct.pack(">I", 9))
    structure = b"".join(chunks)
    pos_struct = 56
    pos_strings = pos_struct + len(structure)
    total = pos_strings + len(strings)
    return (struct.pack(">10I", 0xD00DFEED, total, pos_struct, pos_strings,
                        40, 17, 16, 0, len(strings), len(structure))
            + bytes(16) + structure + strings)

class MergedTests(unittest.TestCase):
    def test_umi_runtime_root_and_two_providers(self):
        r = m.inspect_fdt(sample_fdt())
        self.assertEqual(r["runtime_root_qcom_board_id"], [43, 0])
        self.assertIn("xiaomi umi", r["runtime_root_model"][0])
        self.assertEqual(r["links_observed"], 3)
        self.assertEqual(r["known_regulator_links_resolved"], 2)
        self.assertFalse(r["safe_to_flash"])
        self.assertFalse(r["bootloader_selected_dtbo_index_proven"])

    def test_provider_mapping(self):
        r = m.inspect_fdt(sample_fdt())
        by_name = {x["property"]: x for x in r["ufs_supply_links"]}
        self.assertEqual(by_name["vcc-supply"]["provider_resource"], "ldoa17")
        self.assertEqual(by_name["qcom,vccq-parent-supply"]["provider_resource"], "smpc8")
        self.assertFalse(by_name["vdda-phy-supply"]["provider_phandle_found"])

    def test_no_private_serial_in_json(self):
        self.assertNotIn("PRIVATE12345", json.dumps(m.inspect_fdt(sample_fdt())))

    def test_source_model_absence_not_forced(self):
        r = m.inspect_fdt(sample_fdt(with_model=False))
        self.assertEqual(r["runtime_root_model"], [])
        self.assertFalse(r["bootloader_selected_dtbo_index_proven"])

    def test_wrong_fdt_magic(self):
        data = bytearray(sample_fdt())
        data[0] = 0
        with self.assertRaisesRegex(ValueError, "header"):
            m.inspect_fdt(bytes(data))

    def test_fdt_truncated(self):
        with self.assertRaisesRegex(ValueError, "header"):
            m.inspect_fdt(sample_fdt()[:38])

    def test_unsupported_property_is_filtered(self):
        r = json.dumps(m.inspect_fdt(sample_fdt()))
        self.assertNotIn("serial-number", r)
        self.assertNotIn("status", r)

    def test_wrong_device_aborts_before_root(self):
        calls = []
        def fake_run(args, **kwargs):
            calls.append(args)
            return m.subprocess.CompletedProcess(args, 0, b"dada\n", b"")
        with mock.patch.object(m.subprocess, "run", side_effect=fake_run):
            with self.assertRaisesRegex(ValueError, "not umi"):
                m.collect("adb")
        self.assertEqual(len(calls), 1)

    def test_runner_only_reads_merged_fdt(self):
        import inspect
        src = inspect.getsource(m.collect)
        self.assertIn("/sys/firmware/fdt", src)
        self.assertNotIn("dd of=", src)
        self.assertNotIn("fastboot", src)
        self.assertNotIn("reboot", src)
        self.assertNotIn("mount -", src)

    def test_gates_preserved(self):
        r = m.inspect_fdt(sample_fdt())
        self.assertFalse(r["mainline_electrical_wiring_proven"])
        self.assertFalse(r["safe_to_attempt_mainline_boot"])
        self.assertFalse(r["writes_to_device"])

if __name__ == "__main__":
    unittest.main()
