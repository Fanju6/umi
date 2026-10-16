#!/usr/bin/env python3
"""Collect metadata for 34 previously observed umi reserved-memory DT nodes.

Unprivileged ADB read-only. No raw memory, device IDs, block data, or Root.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

NODES = [
    "adsp_region",
    "cdsp_region",
    "cdsp_secure_heap@8e100000",
    "cnss_wlan_region",
    "cont_splash_region@9c000000",
    "dfps_data_region@9e300000",
    "disp_rdump_region@9c000000",
    "hyp_region@80000000",
    "linux,cma",
    "mailbox_region",
    "mem_dump_region",
    "pil_adsp_region@8bb00000",
    "pil_camera_region@86200000",
    "pil_cdsp_region@87800000",
    "pil_cvp_region@87300000",
    "pil_gpu_region@8681a000",
    "pil_ipa_fw_region@86800000",
    "pil_ipa_gsi_region@86810000",
    "pil_npu_region@86900000",
    "pil_slpi_region@88c00000",
    "pil_spss_region@8e000000",
    "pil_video_region@86e00000",
    "pil_wlan_fw_region@86700000",
    "qseecom_region",
    "qseecom_ta_region",
    "removed_region@80b00000",
    "res_xbl_uefi_log_region@80880000",
    "reserved-memory@80860000",
    "sdsp_region",
    "secure_display_region",
    "smem_region@80900000",
    "sp_region",
    "user_contig_region",
    "xbl_aop_region@80700000"
]
PROPS = ("reg", "size", "alignment", "alloc-ranges")
FLAGS = ("no-map", "reusable")
TAG = "__UMI_RMEM_V2__"
END = "__UMI_RMEM_V2_END__"
MAX_BYTES = 512


def commands():
    s = ['DT=/sys/firmware/devicetree/base',
         '[ -d "$DT/reserved-memory" ] || DT=/proc/device-tree',
         '[ -d "$DT/reserved-memory" ] || exit 4',
         'printf "' + TAG + ' ID %s\\n" "$(getprop ro.product.device)"']
    fields = [("AC", '"$DT/reserved-memory/#address-cells"'),
              ("SC", '"$DT/reserved-memory/#size-cells"')]
    for n in NODES:
        assert re.fullmatch(r"[a-zA-Z0-9,_@.-]+", n)
        base = '"$DT/reserved-memory/' + n
        fields.append((n + "|exists", base + '"'))
        for p in PROPS + FLAGS:
            fields.append((n + "|" + p, base + "/" + p + '"'))
    for key, path in fields:
        if key.endswith("|exists") or key.endswith("|no-map") or key.endswith("|reusable"):
            s.append('if [ -e ' + path + ' ]; then printf "' + TAG + ' ' +
                     key + ' 1\\n"; else printf "' + TAG + ' ' + key + ' 0\\n"; fi')
        else:
            s.append('if [ ! -e ' + path + ' ]; then printf "' + TAG + ' ' + key + ' missing\\n"; '
                     'elif [ ! -r ' + path + ' ]; then printf "' + TAG + ' ' + key + ' unreadable\\n"; '
                     'else printf "' + TAG + ' ' + key + ' "; od -An -v -tx1 ' + path +
                     ' | tr "\\n" " "; printf "\\n"; fi')
    s.append("printf '" + END + "\\n'")
    return "\n".join(s) + "\n"


def decode(raw):
    if raw in ("missing", "unreadable"):
        return raw
    chunks = raw.split()
    if not chunks or len(chunks) > MAX_BYTES or any(
        not re.fullmatch(r"[0-9a-fA-F]{2}", ch) for ch in chunks
    ):
        raise ValueError("invalid hex DT property")
    return bytes.fromhex("".join(chunks))


def cell(data, n):
    if not isinstance(data, bytes) or len(data) != 4 * n:
        raise ValueError("invalid DT cell width")
    return int.from_bytes(data, "big")


def ranges(data, ac, sc):
    stride = 4 * (ac + sc)
    if not isinstance(data, bytes) or not data or len(data) % stride:
        raise ValueError("invalid range length")
    result = []
    for i in range(0, len(data), stride):
        base = int.from_bytes(data[i:i + 4 * ac], "big")
        size = int.from_bytes(data[i + 4 * ac:i + stride], "big")
        if size == 0 or base + size > 2**64:
            raise ValueError("invalid DT range size")
        result.append({"base": f"0x{base:x}", "size": f"0x{size:x}", "bytes": size})
    return result


def parse(raw):
    data = {}
    ended = False
    for line in raw.replace("\r", "").splitlines():
        if line == END:
            ended = True
            break
        if not line.startswith(TAG + " "):
            if line.strip():
                raise ValueError("unexpected shell output")
            continue
        key, sep, value = line[len(TAG) + 1:].partition(" ")
        if not sep or key in data:
            raise ValueError("duplicate or malformed field")
        data[key] = value.strip()
    expected = {"ID", "AC", "SC"} | {
        n + "|" + p for n in NODES for p in ("exists",) + PROPS + FLAGS
    }
    if not ended or set(data) != expected:
        raise ValueError("incomplete whitelist collection")
    if data["ID"] != "umi":
        raise ValueError("device is not umi")
    ac, sc = cell(decode(data["AC"]), 1), cell(decode(data["SC"]), 1)
    if ac not in (1, 2) or sc not in (1, 2):
        raise ValueError("unsupported address/size cell count")
    report = {"schema_version": 1, "device": "umi", "phase": "P0c-reserved",
              "address_cells": ac, "size_cells": sc,
              "safe_to_flash": False, "memory_contents_read": False,
              "regions": {}}
    intervals = []
    for n in NODES:
        present = data[n + "|exists"]
        if present not in ("0", "1"):
            raise ValueError("invalid node presence")
        if present == "0":
            if any(data[n + "|" + p] not in ("missing", "0") for p in PROPS + FLAGS):
                raise ValueError("absent node returned properties")
            report["regions"][n] = {"status": "node_absent"}
            continue
        item = {"status": "observed"}
        for f in FLAGS:
            v = data[n + "|" + f]
            if v not in ("0", "1"):
                raise ValueError("invalid DT boolean")
            item[f.replace("-", "_")] = v == "1"
        for prop in PROPS:
            value = decode(data[n + "|" + prop])
            key = prop.replace("-", "_")
            if isinstance(value, str):
                item[key] = {"status": value}
            elif prop in ("reg", "alloc-ranges"):
                parsed = ranges(value, ac, sc)
                item[key] = {"status": "observed", "ranges": parsed}
                if prop == "reg":
                    for r in parsed:
                        a = int(r["base"], 16)
                        intervals.append((a, a + r["bytes"], n))
            else:
                item[key] = {"status": "observed", "value": f"0x{cell(value, sc):x}"}
        report["regions"][n] = item
    intervals.sort()
    overlaps = []
    for i, (a, b, n) in enumerate(intervals):
        for aa, bb, nn in intervals[i + 1:]:
            if aa >= b:
                break
            if a < bb:
                overlaps.append({"first": n, "second": nn,
                                 "range": [f"0x{max(a, aa):x}", f"0x{min(b, bb):x}"]})
    report["summary"] = {
        "requested_nodes": len(NODES),
        "existing_nodes": sum(v["status"] == "observed" for v in report["regions"].values()),
        "fixed_reg_ranges": len(intervals),
        "total_fixed_reg_bytes": sum(b - a for a, b, _ in intervals),
        "overlaps_for_manual_review": overlaps,
    }
    report["limitations"] = (
        "Only selected live DT metadata. Nodes with size but no reg are dynamic pools "
        "and excluded from fixed overlaps; overlays, aliasing and no-map require review."
    )
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adb", default="adb")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    try:
        result = subprocess.run([args.adb, "shell", "sh"], input=commands(),
                                capture_output=True, text=True, timeout=90, check=False)
        if result.returncode:
            raise RuntimeError(f"adb shell failed: {result.returncode}")
        report = parse(result.stdout)
        output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(output, encoding="utf-8")
            print(f"P0c read-only report saved: {args.output}")
            print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        else:
            print(output)
        return 0
    except (OSError, subprocess.TimeoutExpired, RuntimeError, ValueError) as exc:
        print(f"P0c probe error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
