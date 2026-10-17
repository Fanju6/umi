"""P1b source mapping and readonly sysfs collector regressions."""
import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


probe = load("p1bprobe", "mainline_p1b_probe.py")
audit = load("p1baudit", "mainline_p1b_sources.py")


def sample(category="regulator"):
    result = [f"{probe.MARK}|device|umi|id|umi"]
    ident = "regulator7" if category == "regulator" else "port0"
    for prop in probe.ATTR[category]:
        value = {
            "name": "pm8150_l17", "microvolts": "2950000",
            "state": "enabled", "data_role": "[device] host",
            "power_role": "[sink] source",
        }.get(prop, "missing")
        result.append(f"{probe.MARK}|{category}|{ident}|{prop}|{value}")
    return "\n".join(result) + "\n" + probe.END + "\n"


class P1bTests(unittest.TestCase):
    def setUp(self):
        self.matrix = json.loads(audit.MATRIX.read_text(encoding="utf-8"))

    def test_source_safety(self):
        audit.inspect_matrix(self.matrix)
        self.assertEqual(len(self.matrix["rails"]), 8)

    def test_unreviewed_voltages_rejected(self):
        self.matrix["rails"][0]["live_voltage_verified"] = True
        with self.assertRaisesRegex(ValueError, "电压"):
            audit.inspect_matrix(self.matrix)

    def test_fake_supplier_reference_rejected(self):
        self.matrix["rails"][0]["mainline_candidate"] = "vreg_l17a_elish"
        with self.assertRaises(ValueError):
            audit.inspect_matrix(self.matrix)

    def test_regulator_parse(self):
        report = probe.parse(sample())
        self.assertEqual(report["groups"]["regulator"]["regulator7"]["microvolts"], "2950000")
        self.assertFalse(report["writes_performed"])

    def test_typec_role_parse(self):
        report = probe.parse(sample("typec"))
        self.assertEqual(report["groups"]["typec"]["port0"]["data_role"], "[device] host")

    def test_empty_sections_are_unknown_not_failure(self):
        report = probe.parse(f"{probe.MARK}|device|umi|id|umi\n{probe.END}\n")
        self.assertEqual(report["summary"]["regulator"], 0)
        self.assertIn("缺失", report["limitations"])

    def test_reject_other_device(self):
        with self.assertRaises(ValueError):
            probe.parse(sample().replace("|id|umi", "|id|dagu"))

    def test_reject_truncated(self):
        with self.assertRaises(ValueError):
            probe.parse(sample().replace(probe.END, ""))

    def test_reject_unknown_category_or_attribute(self):
        with self.assertRaises(ValueError):
            probe.parse(sample().replace("|microvolts|", "|serialno|"))

    def test_device_script_never_writes_or_reads_private_identifiers(self):
        script = probe.SCRIPT
        for forbidden in ("su -c", "/dev/block", "/dev/mem", "/proc/cmdline",
                          "ro.serialno", "android_id", "getprop |", "setprop ",
                          "fastboot ", "chmod ", "mount -", "/sys/kernel/debug",
                          "battery/capacity", "battery/health"):
            self.assertNotIn(forbidden, script)

    def test_adb_unprivileged(self):
        response = subprocess.CompletedProcess(["adb", "shell", "sh"], 0, sample(), "")
        with patch.object(probe.subprocess, "run", return_value=response) as call:
            report = probe.collect("adb")
        self.assertEqual(call.call_args.args[0], ["adb", "shell", "sh"])
        self.assertFalse(report["safe_to_flash"])

    def test_typec_glob_filters_partner_cable_and_plugs(self):
        # port[0-9]* matches port0-partner, port0-cable and port0-plug0,
        # but the shell must drop any suffix containing a non-digit.
        script = probe.SCRIPT
        self.assertIn("suffix=${id#port}", script)
        self.assertIn('case "$suffix" in ""|*[!0-9]*) continue ;; esac', script)
        self.assertIn('for node in /sys/class/typec/port[0-9]*;', script)

    def test_bad_typec_directory_is_identified_without_value_dump(self):
        text = sample("typec").replace("|typec|port0|", "|typec|port0-partner|")
        with self.assertRaisesRegex(ValueError, r"typec/port0-partner"):
            probe.parse(text)

    def test_newline_in_attribute_does_not_break_record_format(self):
        # Shell reads only the first line of a multi-line sysfs attribute.
        self.assertIn('head -n 1 "$file"', probe.SCRIPT)
        self.assertNotIn('value=$(cat "$file"', probe.SCRIPT)

    def test_invalid_attribute_name_is_reported(self):
        with self.assertRaisesRegex(ValueError, "采集属性不符合白名单"):
            probe.parse(sample().replace("|microvolts|", "|serialno|"))

    def test_regulator_dot_number_is_standard_kernel_name(self):
        # Locked Linux 4.19 and v6.12 core.c both use regulator.%lu.
        text = sample().replace("|regulator|regulator7|", "|regulator|regulator.7|")
        report = probe.parse(text)
        self.assertEqual(report["groups"]["regulator"]["regulator.7"]["name"], "pm8150_l17")

    def test_scanner_covers_regulator_dot_number_and_previous_pattern(self):
        script = probe.SCRIPT
        self.assertIn("/sys/class/regulator/regulator.[0-9]*", script)
        self.assertIn("/sys/class/regulator/regulator[0-9]*", script)
        self.assertIn("id=" + "$" + "{node##*/}", script)

    def test_reject_unexpected_regulator_child_name(self):
        text = sample().replace("|regulator|regulator7|", "|regulator|regulator.7-device|")
        with self.assertRaisesRegex(ValueError, "regulator/regulator.7-device"):
            probe.parse(text)
