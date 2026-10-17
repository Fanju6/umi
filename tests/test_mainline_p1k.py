"""P1k reproducible observed-parameter provenance and memory reuse safety tests."""
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

p1k = load("p1k_bridge", "scripts/mainline_p1k_ramoops_bridge_audit.py")
probe = load("p1j_probe_for_p1k", "scripts/mainline_p1j_ramoops_params_probe.py")

SAMPLE = """__UMI_P1J_DEVICE__
umi
__UMI_P1J_KERNEL__
4.19.325
__UMI_P1J_BOOT__
1
__UMI_P1J_AB__
false
__UMI_P1J_SLOT__
__UMI_P1J_PSTORE__
yes
__UMI_P1J_PLATFORM__
yes
__UMI_P1J_MEM_ADDRESS__
2952790016
__UMI_P1J_MEM_SIZE__
4194304
__UMI_P1J_CONSOLE_SIZE__
2097152
__UMI_P1J_PMSG_SIZE__
2097152
"""

class P1kTests(unittest.TestCase):
    def setUp(self):
        self.g = json.loads(p1k.GRAPH.read_text(encoding="utf-8"))
        self.mem = json.loads(p1k.P0C.read_text(encoding="utf-8"))
        self.j = json.loads(p1k.P1J.read_text(encoding="utf-8"))

    def check(self):
        return p1k.check(self.g, self.mem, self.j)

    def test_baseline(self):
        r = self.check()
        self.assertEqual(r["size_bytes"], 4 * 1024 * 1024)
        self.assertEqual(r["p0c_fixed_overlap_count"], 0)
        self.assertEqual(r["p0c_dynamic_locations_unknown"], 12)
        self.assertFalse(r["mainline_ram_resource_defined"])
        self.assertFalse(r["safe_to_flash"])

    def test_observed_evidence_does_not_claim_full_json_inspected(self):
        self.assertTrue(self.g["runtime_evidence"]["local_user_report_validated"])
        self.assertFalse(self.g["runtime_evidence"]["raw_p1j_file_inspected_by_assistant"])

    def test_reject_fabricated_runtime_address(self):
        self.g["runtime_evidence"]["observed_parameters"]["mem_address"] = 0x80880000
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.check()

    def test_reject_claim_of_complete_memory_map(self):
        self.g["fixed_memory_audit"]["non_dt_memory_owners_completely_known"] = True
        with self.assertRaisesRegex(ValueError, "incomplete memory map"):
            self.check()

    def test_reject_blind_mainline_dt_addition(self):
        self.g["mainline_612_migration"]["ramoops_dts_node_added"] = True
        with self.assertRaisesRegex(ValueError, "6.12 integration"):
            self.check()

    def test_reject_unsafe_gate(self):
        self.g["gates"]["safe_to_attempt_mainline_boot"] = True
        with self.assertRaisesRegex(ValueError, "unsafe P1k gate"):
            self.check()

    def test_reject_recovery_claim(self):
        self.g["gates"]["recovery_and_earlycon_proven"] = True
        with self.assertRaisesRegex(ValueError, "unsafe P1k gate"):
            self.check()

    def test_detect_fixed_area_collision(self):
        self.mem["regions"]["fixed"][0]["base"] = "0xB0000000"
        with self.assertRaisesRegex(ValueError, "collides"):
            self.check()

    def test_reject_lost_dynamic_pool(self):
        self.mem["regions"]["dynamic"].pop()
        with self.assertRaisesRegex(ValueError, "region list"):
            self.check()

    def test_mainline_source_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "driver drift"):
            p1k.check_mainline_source("", "")

    def test_valid_local_report_attests_without_hardware_claim(self):
        report = probe.parse(SAMPLE)
        result = p1k.p1j.verify_report(report)
        self.assertTrue(result["local_sysfs_values_readable"])
        self.assertTrue(result["values_match_locked_vendor_source"])
        self.assertFalse(result["physical_memory_ownership_verified"])

    def test_modified_report_rejected(self):
        report = probe.parse(SAMPLE)
        report["module_parameter_values"]["mem_size"] = 8388608
        report["parameter_values_match_vendor_candidate"] = False
        self.assertFalse(p1k.p1j.verify_report(report)["values_match_locked_vendor_source"])

    def test_local_report_cli_updates_runtime_while_retaining_block(self):
        report = probe.parse(SAMPLE)
        with tempfile.TemporaryDirectory() as dirname:
            path = Path(dirname) / "p1j-report.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            output = io.StringIO()
            with mock.patch.object(p1k.sys, "argv", ["p1k", "--report", str(path)]), \
                 redirect_stdout(output):
                self.assertEqual(p1k.main(), 0)
            result = json.loads(output.getvalue())
            self.assertTrue(result["local_report_verified"])
            self.assertTrue(result["runtime_metadata_match"])
            self.assertFalse(result["complete_physical_ownership_verified"])
            self.assertFalse(result["safe_to_flash"])

    def test_no_report_remains_unauthenticated_on_client(self):
        stdout = io.StringIO()
        with mock.patch.object(p1k.sys, "argv", ["p1k"]), redirect_stdout(stdout):
            self.assertEqual(p1k.main(), 0)
        result = json.loads(stdout.getvalue())
        self.assertFalse(result["local_report_verified"])
        self.assertIsNone(result["runtime_metadata_match"])

if __name__ == "__main__":
    unittest.main()
