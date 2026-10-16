"""P1j bounded physical interval, pinned source and unprivileged probe tests."""
import importlib.util
import io
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

audit = load("p1j_audit", "scripts/mainline_p1j_ramoops_memory_audit.py")
probe = load("p1j_probe", "scripts/mainline_p1j_ramoops_params_probe.py")

SAMPLE = """__UMI_P1J_DEVICE__
umi
__UMI_P1J_KERNEL__
4.19.325-cip131-st15-perf
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

class P1jTests(unittest.TestCase):
    def setUp(self):
        self.graph = json.loads(audit.CONFIG.read_text(encoding="utf-8"))
        self.p0c = json.loads(audit.P0C.read_text(encoding="utf-8"))
        self.p1i = json.loads(audit.P1I.read_text(encoding="utf-8"))

    def check(self):
        return audit.inspect(self.graph, self.p0c, self.p1i)

    def test_baseline(self):
        r = self.check()
        self.assertEqual(r["p0c_fixed_regions"], 22)
        self.assertEqual(r["p0c_fixed_overlap_count"], 0)
        self.assertEqual(r["source_candidate_end_exclusive"], "0xB0400000")
        self.assertFalse(r["safe_to_flash"])

    def test_end_exclusive_adjacency(self):
        self.assertFalse(audit.overlaps(0xB0000000, 0xB0400000, 0xB0400000, 0xB1400000))
        self.assertTrue(audit.overlaps(0xB0000000, 0xB0400000, 0xB03FFFFF, 0xB1400000))

    def test_reject_collision_with_reserved_memory(self):
        self.p0c["regions"]["fixed"][-1]["base"] = "0xB0200000"
        with self.assertRaisesRegex(ValueError, "OVERLAPS"):
            self.check()

    def test_reject_unsafe_fixed_region_change(self):
        self.graph["p0c_overlap_check"]["not_all_ram_owners_enumerated"] = False
        with self.assertRaisesRegex(ValueError, "partial memory map"):
            self.check()

    def test_reject_claimed_runtime_param_verified(self):
        self.graph["legacy_source_candidate"]["actual_running_parameter_values_verified"] = True
        with self.assertRaisesRegex(ValueError, "unconfirmed"):
            self.check()

    def test_reject_altered_vendor_address(self):
        self.graph["legacy_source_candidate"]["source_physical_base"] = "0x80880000"
        with self.assertRaisesRegex(ValueError, "unconfirmed"):
            self.check()

    def test_reject_fabricated_mainline_compatibility(self):
        self.graph["mainline_diff"]["allow_direct_mainline_ramoops_dts_insertion"] = True
        with self.assertRaisesRegex(ValueError, "compatibility"):
            self.check()

    def test_reject_flash_or_boot_gate(self):
        self.graph["gates"]["safe_to_attempt_mainline_boot"] = True
        with self.assertRaisesRegex(ValueError, "unsafe"):
            self.check()

    def test_reject_p0c_incomplete(self):
        self.p0c["regions"]["dynamic"].pop()
        with self.assertRaisesRegex(ValueError, "counts drifted"):
            self.check()

    def test_probe_matches_source_candidate(self):
        r = probe.parse(SAMPLE)
        self.assertTrue(r["all_four_parameters_readable"])
        self.assertTrue(r["parameter_values_match_vendor_candidate"])
        self.assertTrue(audit.verify_report(r)["values_match_locked_vendor_source"])
        self.assertFalse(r["safe_to_flash"])

    def test_probe_hex_address_supported(self):
        r = probe.parse(SAMPLE.replace("2952790016", "0xB0000000"))
        self.assertTrue(r["parameter_values_match_vendor_candidate"])

    def test_probe_unreadable_is_not_a_negative_hardware_result(self):
        r = probe.parse(SAMPLE.replace("2952790016", "unavailable"))
        self.assertFalse(r["all_four_parameters_readable"])
        self.assertFalse(r["parameter_values_match_vendor_candidate"])
        self.assertIsNone(r["module_parameter_values"]["mem_address"])

    def test_probe_mismatch_blocks_claim(self):
        r = probe.parse(SAMPLE.replace("4194304", "8388608"))
        self.assertFalse(r["parameter_values_match_vendor_candidate"])
        self.assertFalse(audit.verify_report(r)["values_match_locked_vendor_source"])

    def test_probe_reject_other_device(self):
        with self.assertRaisesRegex(ValueError, "not umi"):
            probe.parse(SAMPLE.replace("\numi\n", "\ndagu\n", 1))

    def test_probe_reject_ab_changed(self):
        with self.assertRaisesRegex(ValueError, "non-A/B"):
            probe.parse(SAMPLE.replace("__UMI_P1J_AB__\nfalse",
                                       "__UMI_P1J_AB__\ntrue"))

    def test_probe_reject_non_numeric_values(self):
        with self.assertRaisesRegex(ValueError, "non-numeric"):
            probe.parse(SAMPLE.replace("2952790016", "serial=private"))

    def test_report_rejects_extra_user_device_fields(self):
        r = probe.parse(SAMPLE)
        r["serial"] = "do-not-store"
        with self.assertRaisesRegex(ValueError, "non-whitelisted"):
            audit.verify_report(r)

    def test_report_rejects_claimed_writes(self):
        r = probe.parse(SAMPLE)
        r["writes_device"] = True
        with self.assertRaisesRegex(ValueError, "unsafe report"):
            audit.verify_report(r)

    def test_vendor_sources_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "source drift"):
            audit.verify_sources("", "", "")

    def test_probe_script_non_root_read_only(self):
        s = probe.SCRIPT
        self.assertIn("/sys/module/ramoops/parameters/", s)
        for forbidden in ("su ", "fastboot", "reboot", "dd ", "setprop", "mount ",
                          "/dev/block/", "/proc/cmdline", "/sys/fs/pstore/*",
                          "> /sys/", "> /dev/"):
            self.assertNotIn(forbidden, s)


    def test_probe_empty_sysfs_output_is_unknown(self):
        result = probe.parse(SAMPLE.replace(
            "__UMI_P1J_MEM_ADDRESS__\n2952790016\n",
            "__UMI_P1J_MEM_ADDRESS__\n"))
        self.assertIsNone(result["module_parameter_values"]["mem_address"])
        self.assertFalse(result["all_four_parameters_readable"])
        self.assertFalse(result["parameter_values_match_vendor_candidate"])

    def test_probe_rejects_multiline_sysfs_without_echoing_data(self):
        with self.assertRaisesRegex(probe.ProbeValidationError,
                                    "multiple sysfs lines for: mem_address"):
            probe.parse(SAMPLE.replace("2952790016", "not-a-number\nprivate-value"))

    def test_cli_reports_sanitized_parse_error(self):
        raw = SAMPLE.replace("2952790016", "private-device-output")
        mocked = probe.subprocess.CompletedProcess(
            ["adb"], returncode=0, stdout=raw, stderr="private-adb-stderr")
        errors = io.StringIO()
        with mock.patch.object(probe.subprocess, "run", return_value=mocked), \
             mock.patch.object(probe.sys, "argv", ["probe", "--probe"]), \
             redirect_stderr(errors):
            self.assertEqual(probe.main(), 1)
        message = errors.getvalue()
        self.assertIn("P1j validation failure: non-numeric parameter metadata: mem_address", message)
        self.assertNotIn("private-device-output", message)
        self.assertNotIn("private-adb-stderr", message)

    def test_cli_reports_adb_exit_without_leaking_output(self):
        err = probe.subprocess.CalledProcessError(
            17, ["adb"], output="private-output", stderr="private-stderr")
        errors = io.StringIO()
        with mock.patch.object(probe.subprocess, "run", side_effect=err), \
             mock.patch.object(probe.sys, "argv", ["probe", "--probe"]), \
             redirect_stderr(errors):
            self.assertEqual(probe.main(), 1)
        self.assertIn("exit status 17", errors.getvalue())
        self.assertNotIn("private-", errors.getvalue())

    def test_cli_mocked_adb_writes_sanitized_report(self):
        result = probe.subprocess.CompletedProcess(
            ["adb"], returncode=0, stdout=SAMPLE, stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "sanitized-p1j.json"
            with mock.patch.object(probe.subprocess, "run", return_value=result), \
                 mock.patch.object(probe.sys, "argv",
                                   ["probe", "--probe", "--output", str(output)]), \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(probe.main(), 0)
            audited = audit.verify_report(json.loads(output.read_text(encoding="utf-8")))
            self.assertTrue(audited["values_match_locked_vendor_source"])
            self.assertFalse(audited["safe_to_flash"])

    def test_empty_sysfs_script_fallback(self):
        self.assertIn("value=$(cat", probe.SCRIPT)
        self.assertIn('if [ -n "$value" ]', probe.SCRIPT)
        self.assertIn("else echo unavailable; fi", probe.SCRIPT)

if __name__ == "__main__":
    unittest.main()
