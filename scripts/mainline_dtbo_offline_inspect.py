#!/usr/bin/env python3
"""Inspect umi DTBO v0 container and selected FDT metadata in host RAM.

Device reads: Root ADB binary READ ONLY of dtbo partition (~5.26 MiB).
No raw image saved, no full device-tree contents exposed; only bounded,
whitelisted DTBO IDs, revisions, overlay target-path and UFS/PMIC property
names enter the JSON report. Does not reboot, flash, mount or write.
"""
import argparse
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
BLOCKS = 1347  # 5,517,312 bytes, enough for verified umi DTBO of 5,514,578.
CONFIRMED_TOTAL = 5514578
CONFIRMED_COUNT = 12
DT_MAGIC = 0xD7B7AB1E
FDT_MAGIC = 0xD00DFEED
SAFE_TEXT = re.compile(r"^[A-Za-z0-9,_+./:@ -]{1,200}$")
RELEVANT = re.compile(
    r"^(?:vcc(?:q2?)?-supply|vdd-hba-supply|vdda-(?:phy|pll)-supply|"
    r"qcom,v(?:ddp-ref-clk|ccq-parent)-supply|"
    r"vdd-(?:s[0-9]+|l[0-9]+(?:-l[0-9]+)*)-supply|"
    r"qcom,resource-name)$"
)

def need(cond, msg):
    if not cond:
        raise ValueError(msg)

def safe_strings(buf):
    items = buf.split(b"\0")
    result = []
    for b in items:
        if not b:
            continue
        try:
            value = b.decode("ascii")
        except UnicodeDecodeError:
            continue
        if SAFE_TEXT.fullmatch(value):
            result.append(value)
    return result[:8]

def fdt_metadata(blob):
    need(len(blob) >= 40, "truncated FDT")
    magic, total, off_struct, off_strings, off_mem_rsvmap, version, last_comp, bootcpu, size_strings, size_struct = (
        struct.unpack_from(">10I", blob, 0))
    need(magic == FDT_MAGIC and 40 <= total <= len(blob),
         "invalid overlay FDT header")
    need(off_struct + size_struct <= total and
         off_strings + size_strings <= total and
         off_mem_rsvmap < total and version >= 16,
         "FDT bounds/version invalid")
    struct_end = off_struct + size_struct
    str_end = off_strings + size_strings
    pos = off_struct
    stack = []
    root_compat = []
    root_model = []
    fragments = []
    supplies = []
    property_count = 0
    saw_end = False
    while pos + 4 <= struct_end:
        token = struct.unpack_from(">I", blob, pos)[0]
        pos += 4
        if token == 1:  # FDT_BEGIN_NODE
            end = blob.find(b"\0", pos, struct_end)
            need(end >= 0, "unterminated FDT node")
            name = blob[pos:end].decode("ascii", errors="replace")
            need(len(name) <= 180 and
                 (not name or SAFE_TEXT.fullmatch(name) is not None),
                 "invalid FDT node name")
            stack.append(name)
            need(len(stack) <= 128, "FDT nesting too deep")
            pos = (end + 4) & ~3
        elif token == 2:  # FDT_END_NODE
            need(stack, "FDT stack underflow")
            stack.pop()
        elif token == 3:  # FDT_PROP
            need(pos + 8 <= struct_end and stack, "truncated FDT prop")
            length, name_off = struct.unpack_from(">2I", blob, pos)
            pos += 8
            need(pos + length <= struct_end and name_off < size_strings,
                 "invalid FDT prop bounds")
            name_end = blob.find(b"\0", off_strings + name_off, str_end)
            need(name_end >= 0, "unterminated FDT property name")
            pname = blob[off_strings + name_off:name_end].decode("ascii", errors="replace")
            path = "/" + "/".join(x for x in stack if x)
            value = blob[pos:pos + length]
            property_count += 1
            need(property_count < 100000, "too many FDT properties")
            if len(stack) == 1 and pname == "compatible":
                root_compat = safe_strings(value)
            elif len(stack) == 1 and pname == "model":
                root_model = safe_strings(value)
            elif pname == "target-path" and len(fragments) < 40:
                for item in safe_strings(value):
                    if item.startswith("/"):
                        fragments.append(item)
            elif RELEVANT.fullmatch(pname) and len(supplies) < 80:
                # Only path + property name, never opaque FDT values.
                if len(path) <= 180:
                    supplies.append({"path": path, "property": pname})
            pos = (pos + length + 3) & ~3
        elif token == 4:  # FDT_NOP
            continue
        elif token == 9:  # FDT_END
            saw_end = True
            break
        else:
            raise ValueError("unknown FDT structure token")
    need(saw_end and not stack, "incomplete overlay FDT")
    return {
        "root_compatible": root_compat,
        "root_model": root_model,
        "fragment_target_paths": fragments,
        "power_property_locations": supplies,
        "fdt_structurally_parsed": True,
    }

def inspect_image(data, expected_total=None, expected_count=None):
    need(32 <= len(data) <= MAX_BYTES, "invalid image byte length")
    magic, total, hsize, entry_size, count, offset, page_size, version = (
        struct.unpack_from(">8I", data, 0))
    need(magic == DT_MAGIC and version == 0 and hsize == 32 and
         entry_size == 32 and 1 <= count <= 64 and offset >= 32,
         "not supported Android DTBO v0 header")
    need(total <= len(data) and total <= MAX_BYTES and
         offset + count * entry_size <= total,
         "DTBO entry table out of image bounds")
    if expected_total is not None:
        need(total == expected_total, "DTBO declared size differs from observed")
    if expected_count is not None:
        need(count == expected_count, "DTBO entry count differs from observed")
    table_end = offset + count * entry_size
    items = []
    for i in range(count):
        base = offset + i * entry_size
        length, dt_offset, ident, rev, *custom = struct.unpack_from(">8I", data, base)
        need(length >= 40 and dt_offset >= table_end and
             dt_offset + length <= total, "DTBO FDT range invalid at entry %d" % i)
        fdt = fdt_metadata(data[dt_offset:dt_offset + length])
        items.append({
            "index": i, "id_hex": "0x%08x" % ident,
            "rev_hex": "0x%08x" % rev,
            "custom_hex": ["0x%08x" % x for x in custom],
            "dt_size_bytes": length, "dt_offset_bytes": dt_offset,
            **fdt,
        })
    return {
        "device": "umi", "phase": "dtbo-12-overlays",
        "source": "Root read-only partition bytes parsed in host RAM; only whitelisted metadata kept",
        "dtbo_total_size_bytes": total, "dtbo_entry_count": count,
        "dtbo_table_version": version, "dtbo_page_size": page_size,
        "entries": items,
        "bootloader_overlay_choice_verified": False,
        "runtime_merged_dt_verified_by_this_probe": False,
        "mainline_board_wiring_proven": False,
        "safe_to_attempt_mainline_boot": False,
        "safe_to_flash": False,
        "writes_to_device": False,
    }

def collect(adb="adb"):
    pre = subprocess.run([adb, "shell", "getprop", "ro.product.device"],
                         capture_output=True, timeout=15, check=True)
    need(pre.stdout.strip() == b"umi", "not umi (preflight)")
    # Binary-safe adb exec-out (never adb shell with PTY/CRLF conversion).
    # Fixed dd command reads <= 5.52 MiB from read-only block device.
    command = (
        'for p in /dev/block/by-name/dtbo /dev/block/bootdevice/by-name/dtbo; do '
        '[ -r "$p" ] || continue; '
        'dd if="$p" bs=4096 count=%d 2>/dev/null; exit $?; '
        'done; exit 7' % BLOCKS
    )
    result = subprocess.run(
        [adb, "exec-out", "su", "-c", command],
        capture_output=True, timeout=90, check=True)
    need(len(result.stdout) <= MAX_BYTES, "oversized DTBO data")
    return inspect_image(result.stdout,
                         expected_total=CONFIRMED_TOTAL,
                         expected_count=CONFIRMED_COUNT)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true",
                    help="explicit authorization of Root read-only full DTBO partition content in RAM")
    ap.add_argument("--adb", default="adb")
    ap.add_argument("--output", type=Path, required=True,
                    help="save only filtered metadata as JSON; never the raw DTBO binary")
    args = ap.parse_args()
    if not args.probe:
        ap.error("No device contact without --probe")
    try:
        report = collect(args.adb)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        print("Sanitized DTBO entry metadata saved locally.")
        print(json.dumps({
            "dtbo_entry_count": report["dtbo_entry_count"],
            "fdt_parsed": sum(int(x["fdt_structurally_parsed"]) for x in report["entries"]),
            "power_property_hits": sum(len(x["power_property_locations"]) for x in report["entries"]),
            "bootloader_overlay_choice_verified": False,
            "safe_to_flash": False,
            "output": str(args.output)
        }, ensure_ascii=False, indent=2))
        return 0
    except ValueError as error:
        print("DTBO inspection failed: " + str(error), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        print("Root/ADB read failed (exit %d); raw output hidden" % error.returncode,
              file=sys.stderr)
        return 1
    except (OSError, subprocess.TimeoutExpired):
        print("ADB unavailable or timed out; no writes performed", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
