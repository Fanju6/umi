#!/usr/bin/env python3
"""One-shot root READ-ONLY umi 4.19 hardware metadata survey.

Reads only current regulator state, debugfs regulator hierarchy if already
mounted, iomem *metadata*, UFS PM status and 64 header bytes from
boot/recovery/dtbo (no writes). Raw stdout never saved or echoed.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

BASE, END = 0xB0000000, 0xB0400000
RAILS = {"pm8150_s4", "pm8150_l2", "pm8150_l5", "pm8150_l6",
         "pm8150_l9", "pm8150_l12", "pm8150_l17", "pm8150a_s8",
         "pm8150a_bob"}
SAFE = re.compile(r"^[A-Za-z0-9_.:+/@ -]{0,160}$")
SECTIONS = ("ID", "ROOT", "REGULATORS", "SUMMARY", "IOMEM", "UFS", "HEADERS")
SCRIPT = r"""
printf '\n__UMI_ROOT_ID__\n'
printf '%s|%s|%s|%s\n' "$(getprop ro.product.device)" "$(uname -r)" "$(getprop ro.build.ab_update)" "$(getprop ro.boot.slot_suffix)"
printf '\n__UMI_ROOT_ROOT__\n'
id -u
printf '\n__UMI_ROOT_REGULATORS__\n'
for node in /sys/class/regulator/regulator.[0-9]* /sys/class/regulator/regulator[0-9]*; do
  [ -r "$node/name" ] || continue
  name=$(cat "$node/name" 2>/dev/null) || continue
  case "$name" in
    pm8150_s4|pm8150_l2|pm8150_l5|pm8150_l6|pm8150_l9|pm8150_l12|pm8150_l17|pm8150a_s8|pm8150a_bob)
      val() { if [ -r "$1" ]; then head -n 1 "$1" 2>/dev/null; fi; }
      printf '%s|%s|%s|%s\n' "$name" "$(val "$node/state")" "$(val "$node/microvolts")" "$(val "$node/num_users")"
    ;;
  esac
done
printf '\n__UMI_ROOT_SUMMARY__\n'
if [ -r /sys/kernel/debug/regulator/regulator_summary ]; then
  sed -n '1,1500p' /sys/kernel/debug/regulator/regulator_summary
else echo unavailable; fi
printf '\n__UMI_ROOT_IOMEM__\n'
if [ -r /proc/iomem ]; then sed -n '1,1500p' /proc/iomem; else echo unavailable; fi
printf '\n__UMI_ROOT_UFS__\n'
for node in /sys/bus/platform/devices/*1d84000* /sys/bus/platform/devices/*1d87000*; do
  [ -d "$node" ] || continue
  name=$(basename "$node")
  case "$name" in
    *1d84000*|*1d87000*)
      val() { if [ -r "$1" ]; then head -n 1 "$1" 2>/dev/null; fi; }
      printf '%s|%s|%s\n' "$name" "$(val "$node/power/runtime_status")" "$(val "$node/power/control")"
    ;;
  esac
done
printf '\n__UMI_ROOT_HEADERS__\n'
for name in boot recovery dtbo; do
  seen=no
  for base in /dev/block/by-name /dev/block/bootdevice/by-name; do
    if [ -r "$base/$name" ]; then
      seen=yes
      bytes=$(dd if="$base/$name" bs=64 count=1 2>/dev/null | od -An -tx1 -v | tr -d '\n')
      if [ -n "$bytes" ]; then printf '%s|%s\n' "$name" "$bytes"
      else printf '%s|unavailable\n' "$name"; fi
      break
    fi
  done
  [ "$seen" = yes ] || printf '%s|unavailable\n' "$name"
done
printf '\n__UMI_ROOT_END__\n'
"""

def require(x, msg):
    if not x:
        raise ValueError(msg)

def header(value):
    if value == "unavailable":
        return {"readable": False, "kind": None, "header_version": None}
    words = value.split()
    require(len(words) == 64 and all(re.fullmatch(r"[0-9a-fA-F]{2}", s)
                                     for s in words), "unrecognized 64-byte header")
    raw = bytes.fromhex("".join(words))
    if raw[:8] == b"ANDROID!":
        version = int.from_bytes(raw[40:44], "little")
        return {"readable": True, "kind": "android_boot",
                "header_version": version if version in range(5) else None}
    if raw[:4] == bytes.fromhex("1eabb7d7"):
        return {"readable": True, "kind": "android_dtbo", "header_version": None}
    return {"readable": True, "kind": "unidentified", "header_version": None}

def parse(raw):
    require(len(raw) <= 300000, "oversized ADB output")
    sections = {}
    name = None
    for line in raw.replace("\r", "").splitlines():
        match = re.fullmatch(r"__UMI_ROOT_([A-Z]+)__", line)
        if match:
            name = match.group(1)
            require(name in SECTIONS + ("END",) and name not in sections,
                    "invalid section marker")
            sections[name] = []
        elif name and line:
            sections[name].append(line)
    require(set(sections) == set(SECTIONS + ("END",)) and not sections["END"],
            "incomplete ADB root output")
    ident = sections["ID"]
    require(len(ident) == 1 and re.fullmatch(
        r"umi\|4\.19\.[A-Za-z0-9._+~-]{1,120}\|false\|", ident[0]),
        "not original non-A/B umi 4.19")
    require(sections["ROOT"] == ["0"], "su root UID not confirmed")
    regs = {}
    for line in sections["REGULATORS"]:
        tokens = line.split("|")
        require(len(tokens) == 4 and tokens[0] in RAILS
                and tokens[0] not in regs and
                all(SAFE.fullmatch(v) for v in tokens[1:]),
                "regulator value not whitelisted")
        regs[tokens[0]] = {
            "state": tokens[1] or "unknown",
            "microvolts": int(tokens[2]) if tokens[2].isdigit() else None,
            "num_users": int(tokens[3]) if tokens[3].isdigit() else None,
        }
    summary = sections["SUMMARY"]
    available = summary != ["unavailable"]
    interesting = []
    if available:
        for line in summary[:1500]:
            if not re.search(r"pm8150(?:a)?[_a-z0-9.-]*", line, re.I):
                continue
            line = re.sub(r"\s+", " ", line).strip()
            if SAFE.fullmatch(line):
                interesting.append(line)
            if len(interesting) >= 50:
                break
    iomem = sections["IOMEM"]
    intersections = []
    if iomem != ["unavailable"]:
        for line in iomem[:1500]:
            m = re.match(r"\s*([0-9a-fA-F]{1,16})-([0-9a-fA-F]{1,16})\s*:\s*(.+)", line)
            if not m:
                continue
            start, end = int(m[1], 16), int(m[2], 16) + 1
            if start < END and BASE < end:
                label = m[3].strip()
                intersections.append({
                    "base": hex(start), "end_exclusive": hex(end),
                    "resource": label if SAFE.fullmatch(label) else "redacted"
                })
            if len(intersections) >= 60:
                break
    ufs = []
    for line in sections["UFS"]:
        tokens = line.split("|")
        if len(tokens) != 3:
            continue
        if re.fullmatch(r"[a-zA-Z0-9_.:@-]*1d8[47]000[a-zA-Z0-9_.:@-]*", tokens[0]) \
                and all(SAFE.fullmatch(x) for x in tokens):
            ufs.append({"node": tokens[0], "runtime_status": tokens[1],
                        "control": tokens[2]})
    headers = {}
    for line in sections["HEADERS"]:
        key, sep, value = line.partition("|")
        require(sep and key in {"boot", "recovery", "dtbo"}
                and key not in headers, "invalid partition header label")
        headers[key] = header(value)
    require(set(headers) == {"boot", "recovery", "dtbo"}, "missing header")
    return {
        "stage": "root-baseline", "device": "umi",
        "legacy_kernel": ident[0].split("|")[1],
        "root_uid_confirmed": True,
        "regulators": regs,
        "debugfs_regulator_summary": {
            "available": available, "matching_lines": interesting,
            "physical_parent_wiring_proven": False
        },
        "ramoops_iomem": {
            "available": iomem != ["unavailable"],
            "intersections": intersections,
            "full_memory_ownership_verified": False
        },
        "ufs_nodes": ufs, "partition_headers": headers,
        "source": "root ADB read-only metadata; no raw dump saved",
        "recovery_restoration_proven": False, "mainline_power_ready": False,
        "safe_to_attempt_mainline_boot": False, "safe_to_flash": False,
        "writes_to_device": False
    }

def collect(adb):
    pre = subprocess.run([adb, "shell", "getprop", "ro.product.device"],
                         capture_output=True, text=True, timeout=15, check=True)
    require(pre.stdout.strip() == "umi", "wrong device")
    run = subprocess.run([adb, "shell", "su", "-c", "sh"], input=SCRIPT,
                         capture_output=True, text=True, errors="replace",
                         timeout=70, check=True)
    return parse(run.stdout)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--probe", action="store_true",
                   help="explicit root read-only collection")
    p.add_argument("--output", type=Path)
    p.add_argument("--adb", default="adb")
    a = p.parse_args()
    if not a.probe:
        p.error("use --probe to explicitly authorize Root ADB reads")
    try:
        result = collect(a.adb)
        if a.output:
            a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)
                                + "\n", encoding="utf-8")
            print("Root metadata survey saved locally (sanitized).")
            print(json.dumps({
                "root_confirmed": True,
                "regulator_count": len(result["regulators"]),
                "regulator_summary_available": result["debugfs_regulator_summary"]["available"],
                "iomem_available": result["ramoops_iomem"]["available"],
                "iomem_overlap_records": len(result["ramoops_iomem"]["intersections"]),
                "ufs_count": len(result["ufs_nodes"]),
                "partition_headers": result["partition_headers"],
                "safe_to_flash": False
            }, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ValueError as exc:
        print("Root survey rejected: " + str(exc), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print("Root ADB command failed (exit %d); raw output suppressed."
              % exc.returncode, file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        print("Root ADB command timeout; raw output suppressed.", file=sys.stderr)
        return 1
    except OSError:
        print("ADB executable or local output path inaccessible.", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
