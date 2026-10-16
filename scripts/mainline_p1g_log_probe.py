#!/usr/bin/env python3
"""umi P1g: explicit non-root read-only log-interface probe.

Does not read pstore contents, raw boot partitions, personal identifiers or cmdline.
Never issues reboot, root, mount, flash, fastboot or sysfs writes.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MARKERS = (
    "device", "kernel", "boot_complete", "ab_update", "slot_suffix",
    "pstore_dir", "pstore_fs", "pstore_kinds",
)
KINDS = ("console", "dmesg", "pmsg", "ftrace")
DEVICE_SCRIPT = r"""
section() { printf '\n__UMI_P1G_%s__\n' "$1"; }
section device; getprop ro.product.device
section kernel; uname -r
section boot_complete; getprop sys.boot_completed
section ab_update; getprop ro.build.ab_update
section slot_suffix; getprop ro.boot.slot_suffix
section pstore_dir
if [ -d /sys/fs/pstore ]; then echo yes; else echo no; fi
section pstore_fs
if grep -q '[[:space:]]/sys/fs/pstore[[:space:]]pstore[[:space:]]' /proc/mounts; then echo yes; else echo no; fi
section pstore_kinds
for item in /sys/fs/pstore/*; do
    [ -f "$item" ] || continue
    case "${item##*/}" in
        console-ramoops*) echo console ;;
        dmesg-ramoops*) echo dmesg ;;
        pmsg-ramoops*) echo pmsg ;;
        ftrace-ramoops*) echo ftrace ;;
    esac
done
"""

def require(value, reason):
    if not value:
        raise ValueError(reason)

def parse(output):
    sections = {}
    current = None
    for raw in output.splitlines():
        line = raw.strip()
        if line.startswith("__UMI_P1G_") and line.endswith("__"):
            name = line[len("__UMI_P1G_"):-2].lower()
            require(name in MARKERS and name not in sections,
                    "unexpected report marker")
            sections[name] = []
            current = name
        elif line and current is not None:
            sections[current].append(line)
        elif line:
            raise ValueError("unexpected output outside marker")
    require(set(sections) == set(MARKERS), "incomplete report")
    require(sections["device"] == ["umi"], "not umi")
    require(len(sections["kernel"]) == 1 and
            re.fullmatch(r"[A-Za-z0-9._+~-]{1,128}", sections["kernel"][0]),
            "invalid kernel version")
    require(sections["boot_complete"] == ["1"], "Android not boot complete")
    require(sections["ab_update"] == ["false"] and
            sections["slot_suffix"] == [], "non-A/B status changed")
    for key in ("pstore_dir", "pstore_fs"):
        require(len(sections[key]) == 1 and
                sections[key][0] in ("yes", "no"), "invalid pstore flag")
    require(set(sections["pstore_kinds"]).issubset(KINDS),
            "invalid pstore record classification")
    return {
        "schema_version": 1, "stage": "P1g", "device": "umi",
        "source": "explicit non-root read-only adb shell",
        "observed_kernel": sections["kernel"][0],
        "non_ab_observed": True,
        "pstore_directory_present": sections["pstore_dir"] == ["yes"],
        "pstore_filesystem_mounted": sections["pstore_fs"] == ["yes"],
        "pstore_record_types_visible": sorted(set(sections["pstore_kinds"])),
        "pstore_survives_crash_verified": False,
        "earlycon_verified": False, "recovery_path_tested": False,
        "safe_to_attempt_mainline_boot": False, "safe_to_flash": False,
        "writes_to_device": False,
        "note": "mount/record presence is not evidence of retained crash logs or wired UART",
    }

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true",
                    help="explicitly run fixed non-root ADB read-only commands")
    ap.add_argument("--output", type=Path, help="save sanitized JSON locally")
    args = ap.parse_args()
    if not args.probe:
        ap.error("No device operation performed; use --probe explicitly.")
    try:
        run = subprocess.run(["adb", "shell", "sh", "-c", DEVICE_SCRIPT],
                             text=True, capture_output=True, timeout=25, check=True)
        report = parse(run.stdout.replace("\r", ""))
        data = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(data, encoding="utf-8")
            print("P1g: local sanitized read-only report saved")
            print(json.dumps({k: report[k] for k in (
                "pstore_directory_present", "pstore_filesystem_mounted",
                "pstore_record_types_visible", "safe_to_flash")},
                ensure_ascii=False, indent=2))
        else:
            print(data)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError):
        print("P1g probe aborted: verify ADB, umi identity, completed boot and "
              "non-A/B state; no device changes performed.", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
