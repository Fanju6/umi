"""Root one-shot scanner regression: no phone or Root required in CI."""
import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "root_survey", ROOT / "scripts/mainline_root_hardware_survey.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def hdr(magic, version=2):
    b = bytearray(64)
    b[:len(magic)] = magic
    if magic == b"ANDROID!":
        b[40:44] = version.to_bytes(4, "little")
    return " ".join("%02x" % x for x in b)

def output():
    return "\n".join([
        "__UMI_ROOT_ID__", "umi|4.19.325-test|false|",
        "__UMI_ROOT_ROOT__", "0",
        "__UMI_ROOT_REGULATORS__",
        "pm8150_l6|enabled|1200000|2",
        "pm8150_l17|enabled|2504000|1",
        "__UMI_ROOT_SUMMARY__",
        "regulator use open bypass",
        "pm8150_l6 1 2 1200000 UFS",
        "private_serial_012345",
        "__UMI_ROOT_DTREE__", "rpmh-regulator-ldoa6|ldoa6",
        "rpmh-regulator-smpa4|smpa4", "private-secret-node|nope",
        "__UMI_ROOT_IOMEM__",
        "b0000000-b03fffff : reserved",
        "b0400000-b13fffff : disp_rdump",
        "30000000-30000fff : unrelated",
        "__UMI_ROOT_UFS__",
        "1d84000.ufshc|active|auto",
        "__UMI_ROOT_HEADERS__",
        "boot|" + hdr(b"ANDROID!", 2),
        "recovery|" + hdr(b"ANDROID!", 2),
        "dtbo|" + hdr(bytes.fromhex("1eabb7d7")),
        "__UMI_ROOT_END__", "",
    ])

class RootSurveyTests(unittest.TestCase):
    def test_accepts_authorized_umi(self):
        v = m.parse(output())
        self.assertTrue(v["root_uid_confirmed"])
        self.assertEqual(v["partition_headers"]["boot"]["header_version"], 2)
        self.assertEqual(v["partition_headers"]["dtbo"]["kind"], "android_dtbo")
        self.assertEqual(len(v["regulators"]), 2)
        self.assertEqual(len(v["ufs_nodes"]), 1)
        self.assertEqual(len(v["ramoops_iomem"]["intersections"]), 1)
        self.assertFalse(v["safe_to_flash"])
        self.assertFalse(v["recovery_restoration_proven"])

    def test_runtime_dtree_keeps_only_known_resource_ids(self):
        v = m.parse(output())
        self.assertEqual(len(v["runtime_device_tree"]["selected_rpmh_resources"]), 2)
        self.assertFalse(v["runtime_device_tree"]["pcb_wiring_verified"])
        self.assertNotIn("private-secret-node", json.dumps(v))

    def test_root_permission_required(self):
        with self.assertRaisesRegex(ValueError, "root UID"):
            m.parse(output().replace("__UMI_ROOT_ROOT__\n0",
                                     "__UMI_ROOT_ROOT__\n2000"))

    def test_other_device_rejected(self):
        with self.assertRaisesRegex(ValueError, "umi"):
            m.parse(output().replace("umi|4.19", "dagu|4.19"))

    def test_other_kernel_rejected(self):
        with self.assertRaisesRegex(ValueError, "4.19"):
            m.parse(output().replace("4.19.325", "6.12.0"))

    def test_physical_memory_not_proven_from_iomem(self):
        d = m.parse(output())
        self.assertFalse(d["ramoops_iomem"]["full_memory_ownership_verified"])

    def test_no_raw_imei_or_unrelated_resource_retained(self):
        d = json.dumps(m.parse(output()))
        self.assertNotIn("private_serial", d)
        self.assertNotIn("unrelated", d)

    def test_unavailable_debug_and_iomem_are_not_failure(self):
        s = output()
        s = s.replace("regulator use open bypass\npm8150_l6 1 2 1200000 UFS\nprivate_serial_012345",
                      "unavailable")
        s = s.replace("b0000000-b03fffff : reserved\nb0400000-b13fffff : disp_rdump\n30000000-30000fff : unrelated",
                      "unavailable")
        v = m.parse(s)
        self.assertFalse(v["ramoops_iomem"]["available"])
        self.assertFalse(v["debugfs_regulator_summary"]["available"])

    def test_unknown_header_is_reported_not_guessed(self):
        s = output().replace("dtbo|" + hdr(bytes.fromhex("1eabb7d7")),
                             "dtbo|unavailable")
        self.assertFalse(m.parse(s)["partition_headers"]["dtbo"]["readable"])

    def test_incomplete_data_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            m.parse(output().replace("__UMI_ROOT_END__", ""))

    def test_unknown_regulator_rejected(self):
        with self.assertRaisesRegex(ValueError, "regulator"):
            m.parse(output().replace("pm8150_l6|enabled", "private_rail|enabled"))

    def test_device_script_only_read_operations(self):
        s = m.SCRIPT
        for required in ("id -u", "regulator_summary", "/proc/iomem",
                         "bs=64 count=1", "power/runtime_status", "getprop"):
            self.assertIn(required, s)
        for forbidden in ("of=", "fastboot", "reboot", "setprop",
                          "mount -", "echo 1 >", "kill -", "sysrq-trigger"):
            self.assertNotIn(forbidden, s)

    def test_preflight_identity_before_root(self):
        args = []
        def fake_run(cmd, **kwargs):
            args.append(cmd)
            return m.subprocess.CompletedProcess(
                cmd, 0,
                stdout="dagu\n" if len(args) == 1 else output(), stderr="")
        with mock.patch.object(m.subprocess, "run", side_effect=fake_run):
            with self.assertRaisesRegex(ValueError, "wrong device"):
                m.collect("adb")
        self.assertEqual(len(args), 1)

if __name__ == "__main__":
    unittest.main()
