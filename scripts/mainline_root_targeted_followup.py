#!/usr/bin/env python3
"""Optional targeted root metadata follow-up for umi: DTBO signature and debugfs path.

This does not mount filesystems, read full partitions, dump DTBs or write data.
Only the first 64 bytes of dtbo are read and parsed locally; no raw dump saved.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SHELL = r"""
printf '__UMI_EXTRA_ID__|%s|%s|%s\n' "$(getprop ro.product.device)" "$(uname -r)" "$(id -u)"
printf '__UMI_EXTRA_DEBUG__|'
if grep -q ' debugfs ' /proc/mounts; then echo mounted; else echo unmounted; fi
for path in /sys/kernel/debug/regulator/regulator_summary /d/regulator/regulator_summary; do
  case "$path" in
    /sys/kernel/debug/*) alias=sys_kernel_debug ;;
    /d/*) alias=d ;;
  esac
  if [ -r "$path" ]; then
    printf '__UMI_EXTRA_SUMMARY__|%s|readable\n' "$alias"
  else
    printf '__UMI_EXTRA_SUMMARY__|%s|unavailable\n' "$alias"
  fi
done
printf '__UMI_EXTRA_DTBO__|'
found=no
for base in /dev/block/by-name /dev/block/bootdevice/by-name; do
  if [ -r "$base/dtbo" ]; then
    found=yes
    bytes=$(dd if="$base/dtbo" bs=64 count=1 2>/dev/null | od -An -tx1 -v | tr -d '\n')
    if [ -n "$bytes" ]; then echo "$bytes"; else echo unavailable; fi
    break
  fi
done
[ "$found" = yes ] || echo unavailable
printf '__UMI_EXTRA_END__\n'
"""

def require(cond, message):
    if not cond:
        raise ValueError(message)

def inspect_dtbo(raw):
    if raw == "unavailable":
        return {"readable": False, "format": "unavailable", "magic_hex": None,
                "dt_table": None}
    words = raw.split()
    require(len(words) == 64 and
            all(re.fullmatch(r"[0-9a-fA-F]{2}", w) for w in words),
            "unexpected 64-byte DTBO header length")
    data = bytes.fromhex("".join(words))
    magic = data[:4]
    out = {"readable": True, "format": "unidentified",
           "magic_hex": magic.hex(), "dt_table": None}
    if magic == bytes.fromhex("d7b7ab1e"):
        size = int.from_bytes(data[4:8], "big")
        header = int.from_bytes(data[8:12], "big")
        entry = int.from_bytes(data[12:16], "big")
        count = int.from_bytes(data[16:20], "big")
        offset = int.from_bytes(data[20:24], "big")
        version = int.from_bytes(data[28:32], "big")
        plausible = (header == 32 and entry >= 32 and
                     0 < count <= 1024 and 0 < size <= 128*1024*1024 and
                     offset >= 32 and offset + entry*count <= size)
        out["format"] = "android_dt_table" if plausible else "android_dt_table_malformed_or_unusual"
        out["dt_table"] = {
            "total_size_bytes": size, "header_size_bytes": header,
            "entry_size_bytes": entry, "entry_count": count,
            "entries_offset_bytes": offset, "version": version,
            "basic_structure_plausible": plausible,
        }
    elif magic == b"QCDT":
        out["format"] = "qualcomm_qcdt_candidate"
    elif magic == bytes.fromhex("d00dfeed"):
        out["format"] = "raw_fdt_candidate"
    elif all(b == 0 for b in data):
        out["format"] = "zero_filled_header"
    elif all(b == 255 for b in data):
        out["format"] = "ff_filled_header"
    return out

def parse(text):
    require(len(text) <= 12000, "oversized output")
    fields = {}
    for line in text.replace("\r", "").splitlines():
        if line == "__UMI_EXTRA_END__":
            require("end" not in fields, "duplicate end marker")
            fields["end"] = True
            continue
        if not line.startswith("__UMI_EXTRA_"):
            require(not line.strip(), "unexpected unmarked output")
            continue
        key, sep, value = line.partition("|")
        require(sep and key in ("__UMI_EXTRA_ID__", "__UMI_EXTRA_DEBUG__",
                                "__UMI_EXTRA_SUMMARY__", "__UMI_EXTRA_DTBO__"),
                "unknown metadata marker")
        fields.setdefault(key, []).append(value)
    require(fields.get("end") is True and
            set(fields) == {"end", "__UMI_EXTRA_ID__", "__UMI_EXTRA_DEBUG__",
                            "__UMI_EXTRA_SUMMARY__", "__UMI_EXTRA_DTBO__"},
            "missing report component")
    ids = fields["__UMI_EXTRA_ID__"]
    require(len(ids) == 1 and
            re.fullmatch(r"umi\|4\.19\.[A-Za-z0-9._+~-]{1,120}\|0", ids[0]),
            "device/kernel/root identity changed")
    debug = fields["__UMI_EXTRA_DEBUG__"]
    require(len(debug) == 1 and debug[0] in ("mounted", "unmounted"),
            "invalid debugfs mount observation")
    statuses = {}
    for line in fields["__UMI_EXTRA_SUMMARY__"]:
        alias, sep, value = line.partition("|")
        require(sep and alias in ("sys_kernel_debug", "d") and
                value in ("readable", "unavailable") and alias not in statuses,
                "bad debugfs summary status")
        statuses[alias] = value
    require(set(statuses) == {"sys_kernel_debug", "d"},
            "missing debugfs paths")
    dtbo = fields["__UMI_EXTRA_DTBO__"]
    require(len(dtbo) == 1, "missing DTBO header metadata")
    return {
        "device": "umi", "phase": "root-targeted-followup",
        "debugfs": {"already_mounted": debug[0] == "mounted",
                    "paths": statuses},
        "dtbo_header": inspect_dtbo(dtbo[0]),
        "recovery_boot_tested": False,
        "mainline_board_wiring_proven": False,
        "safe_to_attempt_mainline_boot": False,
        "safe_to_flash": False,
        "writes_to_device": False,
    }

def collect(adb):
    pre = subprocess.run([adb, "shell", "getprop", "ro.product.device"],
                         text=True, capture_output=True, timeout=15, check=True)
    require(pre.stdout.strip() == "umi", "not umi (preflight)")
    result = subprocess.run([adb, "shell", "su", "-c", "sh"], input=SHELL,
                            text=True, errors="replace", capture_output=True,
                            timeout=30, check=True)
    return parse(result.stdout)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--adb", default="adb")
    ap.add_argument("--output", type=Path)
    a = ap.parse_args()
    if not a.probe:
        ap.error("Device access requires explicit --probe")
    try:
        result = collect(a.adb)
        data = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if a.output:
            a.output.write_text(data, encoding="utf-8")
            print("Root DTBO/debugfs follow-up saved as local JSON")
        print(data)
        return 0
    except ValueError as e:
        print("Root follow-up validation failed: " + str(e), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as e:
        print("Root ADB failed (exit %d); raw output suppressed." %
              e.returncode, file=sys.stderr)
        return 1
    except (OSError, subprocess.TimeoutExpired):
        print("Root ADB timeout or unavailable; no writes.", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
