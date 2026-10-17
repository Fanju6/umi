#!/usr/bin/env python3
"""P1i: explicit non-root read-only identification of umi ramoops registration.

Read only names/presence of known sysfs nodes and a DT *compatible* marker.
Never read raw DT reg, RAM, pstore log content, cmdline or block devices.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MARKERS = (
    "device", "kernel", "boot_complete", "ab_update", "slot_suffix",
    "pstore_mount", "platform_ramoops", "dt_ramoops", "module_params",
)
SCRIPT = r"""
section() { printf '\n__UMI_P1I_%s__\n' "$1"; }
section device; getprop ro.product.device
section kernel; uname -r
section boot_complete; getprop sys.boot_completed
section ab_update; getprop ro.build.ab_update
section slot_suffix; getprop ro.boot.slot_suffix
section pstore_mount
if grep -q '[[:space:]]/sys/fs/pstore[[:space:]]pstore[[:space:]]' /proc/mounts; then echo yes; else echo no; fi
section platform_ramoops
found=no
for item in /sys/bus/platform/devices/ramoops /sys/bus/platform/devices/ramoops.*; do
    if [ -d "$item" ]; then found=yes; fi
done
echo "$found"
section dt_ramoops
found=no
for item in /sys/firmware/devicetree/base/ramoops /sys/firmware/devicetree/base/ramoops@* /sys/firmware/devicetree/base/reserved-memory/*; do
    if [ -f "$item/compatible" ] && grep -a -q 'ramoops' "$item/compatible"; then found=yes; fi
done
echo "$found"
section module_params
if [ -d /sys/module/ramoops/parameters ]; then echo yes; else echo no; fi
"""

def require(ok, msg):
    if not ok:
        raise ValueError(msg)

def parse(output):
    s = {}
    current = None
    for raw in output.splitlines():
        line = raw.strip()
        if line.startswith("__UMI_P1I_") and line.endswith("__"):
            name = line[len("__UMI_P1I_"):-2].lower()
            require(name in MARKERS and name not in s, "unexpected/duplicate marker")
            s[name] = []
            current = name
        elif current is not None and line:
            s[current].append(line)
        elif line:
            raise ValueError("unmarked output")
    require(set(s) == set(MARKERS), "missing report sections")
    require(s["device"] == ["umi"], "not umi")
    require(len(s["kernel"]) == 1 and
            re.fullmatch(r"4\.19\.[0-9A-Za-z._+~-]{1,120}", s["kernel"][0]),
            "unexpected kernel")
    require(s["boot_complete"] == ["1"], "device not fully booted")
    require(s["ab_update"] == ["false"] and s["slot_suffix"] == [],
            "device A/B observation changed")
    for name in ("pstore_mount", "platform_ramoops", "dt_ramoops", "module_params"):
        require(s[name] in (["yes"], ["no"]), "invalid Boolean evidence")
    return {
        "schema_version": 1, "phase": "P1i", "device": "umi",
        "source": "non-root explicit read-only adb metadata",
        "legacy_kernel": s["kernel"][0],
        "pstore_mounted": s["pstore_mount"] == ["yes"],
        "ramoops_platform_device_name_observed": s["platform_ramoops"] == ["yes"],
        "ramoops_dt_compatible_candidate_observed": s["dt_ramoops"] == ["yes"],
        "ramoops_module_parameters_dir_present": s["module_params"] == ["yes"],
        "physical_address_read": False, "ram_contents_read": False,
        "pstore_log_contents_read": False, "physical_region_verified": False,
        "ramoops_backend_mapping_verified": False,
        "recovery_tested": False, "safe_to_attempt_mainline_boot": False,
        "safe_to_flash": False, "writes_to_device": False,
        "limitations": "Presence/absence in searched paths is NOT complete registration or physical-memory proof",
    }

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true",
                    help="explicitly opt in to fixed non-root ADB metadata commands")
    ap.add_argument("--output", type=Path,
                    help="optional private local sanitized JSON report")
    args = ap.parse_args()
    if not args.probe:
        ap.error("No device request issued. Supply --probe explicitly.")
    try:
        run = subprocess.run(["adb", "shell", "sh", "-c", SCRIPT],
                             capture_output=True, text=True, timeout=25, check=True)
        report = parse(run.stdout.replace("\r", ""))
        content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(content, encoding="utf-8")
            print("P1i: sanitized evidence saved locally")
            print(json.dumps({k: report[k] for k in (
                "pstore_mounted", "ramoops_platform_device_name_observed",
                "ramoops_dt_compatible_candidate_observed",
                "ramoops_module_parameters_dir_present",
                "physical_region_verified", "safe_to_flash"
            )}, ensure_ascii=False, indent=2))
        else:
            print(content)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError):
        print("P1i probe aborted: verify connected umi and old 4.19 baseline; "
              "no device write attempted.", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
