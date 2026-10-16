#!/usr/bin/env python3
"""P1j: opt-in non-root read-only sysfs RAMOOPS parameter metadata.

Read ONLY four /sys/module/ramoops/parameters numeric values. No pstore log
contents, /proc/cmdline, /proc/iomem, device memory, partitions or Root.
Values may be unavailable to unprivileged adb; no privilege escalation.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

PARAMS = ("mem_address", "mem_size", "console_size", "pmsg_size")
MARKERS = ("device", "kernel", "boot", "ab", "slot", "pstore",
           "platform") + PARAMS
SCRIPT = r"""
section() { printf '\n__UMI_P1J_%s__\n' "$1"; }
section device; getprop ro.product.device
section kernel; uname -r
section boot; getprop sys.boot_completed
section ab; getprop ro.build.ab_update
section slot; getprop ro.boot.slot_suffix
section pstore
if grep -q '[[:space:]]/sys/fs/pstore[[:space:]]pstore[[:space:]]' /proc/mounts; then echo yes; else echo no; fi
section platform
found=no
for item in /sys/bus/platform/devices/ramoops /sys/bus/platform/devices/ramoops.*; do
    if [ -d "$item" ]; then found=yes; fi
done
echo "$found"
for key in mem_address mem_size console_size pmsg_size; do
    section "$key"
    path="/sys/module/ramoops/parameters/$key"
    if [ -r "$path" ]; then
        value=$(cat "$path" 2>/dev/null) || value=
        if [ -n "$value" ]; then printf '%s\n' "$value"; else echo unavailable; fi
    else
        echo unavailable
    fi
done
"""

class ProbeValidationError(ValueError):
    """Only developer-authored, sanitized validation messages."""


def require(ok, message):
    if not ok:
        raise ProbeValidationError(message)

def parse(source):
    sections = {}
    name = None
    for raw in source.splitlines():
        item = raw.strip()
        if item.startswith("__UMI_P1J_") and item.endswith("__"):
            name = item[len("__UMI_P1J_"):-2].lower()
            require(name in MARKERS and name not in sections,
                    "invalid or duplicate report marker")
            sections[name] = []
        elif item and name is not None:
            sections[name].append(item)
        elif item:
            raise ProbeValidationError("unexpected unmarked ADB stdout")
    require(set(sections) == set(MARKERS), "incomplete report")
    require(sections["device"] == ["umi"], "not umi")
    require(len(sections["kernel"]) == 1 and
            re.fullmatch(r"4\.19\.[0-9A-Za-z._+~-]{1,120}",
                         sections["kernel"][0]), "not 4.19 baseline")
    require(sections["boot"] == ["1"] and
            sections["ab"] == ["false"] and sections["slot"] == [],
            "device boot state/non-A/B identity changed")
    require(sections["pstore"] == ["yes"] and
            sections["platform"] == ["yes"], "P1i pstore/platform observations changed")
    parsed = {}
    for key in PARAMS:
        require(len(sections[key]) <= 1, "multiple sysfs lines for: " + key)
        if not sections[key]:
            parsed[key] = None  # empty sysfs read is unavailable, not a parse crash
            continue
        raw = sections[key][0]
        if raw == "unavailable":
            parsed[key] = None
            continue
        require(bool(re.fullmatch(r"(?:0[xX][0-9a-fA-F]+|[0-9]+)", raw)),
                "non-numeric parameter metadata: " + key)
        parsed[key] = int(raw, 16 if raw.lower().startswith("0x") else 10)
        require(0 <= parsed[key] < (1 << 64), "out-of-range parameter")
    available = all(parsed[k] is not None for k in PARAMS)
    matched = available and parsed == {
        "mem_address": 0xB0000000, "mem_size": 4 * 1024 * 1024,
        "console_size": 2 * 1024 * 1024,
        "pmsg_size": 2 * 1024 * 1024}
    return {
        "schema_version": 1, "phase": "P1j", "device": "umi",
        "source": "explicit non-root adb sysfs parameter metadata",
        "legacy_kernel": sections["kernel"][0],
        "pstore_mounted": True, "platform_ramoops_observed": True,
        "module_parameter_values": parsed,
        "all_four_parameters_readable": available,
        "parameter_values_match_vendor_candidate": matched,
        "reads_pstore_contents": False,
        "reads_physical_memory_contents": False,
        "writes_device": False, "safe_to_flash": False,
        "safe_to_attempt_mainline_boot": False,
        "limits": "sysfs parameter metadata only; cannot prove mapping ownership or crash survival",
    }

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true",
                    help="explicitly run four non-root, read-only module-parameter queries")
    ap.add_argument("--output", type=Path, help="save sanitized local JSON; never uploaded")
    args = ap.parse_args()
    if not args.probe:
        ap.error("Not connected to any device: specify --probe explicitly.")
    try:
        r = subprocess.run(["adb", "shell", "sh", "-c", SCRIPT],
                           capture_output=True, text=True, check=True, timeout=25)
        report = parse(r.stdout.replace("\r", ""))
        output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(output, encoding="utf-8")
            print("P1j sanitized read-only report saved locally")
            print(json.dumps({k: report[k] for k in (
                "module_parameter_values", "all_four_parameters_readable",
                "parameter_values_match_vendor_candidate",
                "safe_to_flash")}, ensure_ascii=False, indent=2))
        else:
            print(output)
        return 0
    except ProbeValidationError as exc:
        # Message contains only hardcoded section names and assertions, never raw values.
        print("P1j validation failure: " + str(exc), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print("P1j ADB shell command failed (exit status %d); raw output hidden."
              % exc.returncode, file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        print("P1j ADB shell timeout; raw output hidden.", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print("P1j ADB executable or local output directory not found.", file=sys.stderr)
        return 1
    except (OSError, ValueError, subprocess.SubprocessError):
        print("P1j probe aborted during local I/O or numeric decoding; "
              "raw device output hidden.", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
