#!/usr/bin/env python3
"""CI-only comparison of Xiaomi umi vendor DTBO[11] with two base DTBs.

The user-selected DTBO is kept wholly in runner memory / temporary files.
Only summarized results and bounded tool error codes are reported.
Never assembles a flash image or touches a device.
"""
import argparse
import json
import struct
import subprocess
import tempfile
from pathlib import Path

MAGIC_DTBO = 0xD7B7AB1E
MAGIC_FDT = 0xD00DFEED
MAX_IMAGE = 8 * 1024 * 1024
MAX_DTBO_PARTITION = 34 * 1024 * 1024  # umi dtbo partition is 32 MiB
EXPECTED_COUNT = 12
EXPECTED_UMI_INDEX = 11
EXPECTED_UMI_MODEL = b"Qualcomm Technologies, Inc. xiaomi umi"


def need(ok, message):
    if not ok:
        raise ValueError(message)


def parse_dtbo(blob):
    need(32 <= len(blob) <= MAX_DTBO_PARTITION,
         "unexpected DTBO partition/image length")
    magic, total, hsize, esize, count, offset, page_size, version = struct.unpack_from(
        ">8I", blob)
    need(magic == MAGIC_DTBO and hsize == 32 and esize == 32 and
         count == EXPECTED_COUNT and version == 0 and
         0 < total <= min(len(blob), MAX_IMAGE) and offset >= 32 and
         offset + count * 32 <= total,
         "not the expected 12-entry Android DT table v0")
    # Published dtbo.img can contain a complete padded 32 MiB partition.
    # Entries remain bounded by the DT header declared total_size.
    suffix = blob[total:]
    need(not suffix or all(b == 0 for b in suffix) or
         all(b == 0xff for b in suffix),
         "nonempty unexpected bytes after declared DTBO table")
    entries = []
    for index in range(count):
        pos = offset + index * esize
        size, foff, ident, revision, c0, c1, c2, c3 = struct.unpack_from(
            ">8I", blob, pos)
        need(40 <= size < MAX_IMAGE and
             foff >= offset + count * esize and
             foff + size <= total, "invalid DTBO FDT entry")
        payload = blob[foff:foff + size]
        need(int.from_bytes(payload[:4], "big") == MAGIC_FDT and
             int.from_bytes(payload[4:8], "big") <= size,
             "invalid DTBO overlay header")
        entries.append({"index": index, "size": size, "data": payload})
    need(EXPECTED_UMI_MODEL in entries[EXPECTED_UMI_INDEX]["data"],
         "index 11 lacks verified umi model")
    return entries, {"entry_count": count, "declared_size_bytes": total,
                     "downloaded_partition_bytes": len(blob),
                     "trailing_padding_bytes": len(blob) - total,
                     "selected_index": EXPECTED_UMI_INDEX,
                     "selected_size_bytes": entries[11]["size"],
                     "umi_model_matched": True}


def find_dtb_segments(blob):
    """Support one FDT or a concatenated original Android boot v2 DTB pack."""
    need(40 <= len(blob) < MAX_IMAGE, "unexpected boot DTB length")
    segments = []
    at = 0
    while at + 40 <= len(blob):
        if blob[at:at + 4] != b"\xd0\x0d\xfe\xed":
            if all(b == 0 for b in blob[at:]):
                break
            raise ValueError("boot DTB isn't a concatenated FDT sequence")
        size = int.from_bytes(blob[at + 4:at + 8], "big")
        need(40 <= size <= len(blob) - at, "invalid boot FDT segment size")
        segments.append(blob[at:at + size])
        at = (at + size + 3) & ~3
    need(1 <= len(segments) <= 32, "unexpected number of boot DTB entries")
    return segments


def verify_dtb_identity(dtb):
    need(dtb[:4] == b"\xd0\x0d\xfe\xed", "invalid mainline FDT magic")
    need(b"Xiaomi Mi 10 (umi)" in dtb, "not the experimental mainline umi DTB")


def merge_probe(base, overlay, work, stem):
    b = work / (stem + "-base.dtb")
    o = work / (stem + "-merged.dtb")
    b.write_bytes(base)
    p = subprocess.run(["fdtoverlay", "-i", str(b), "-o", str(o), str(overlay)],
                       capture_output=True, text=True, errors="replace",
                       timeout=60, check=False)
    if p.returncode:
        # No need to publish absolute paths or unbounded logs.
        cleaned = (p.stderr + " " + p.stdout).replace(str(b), "<base>").replace(
            str(overlay), "<overlay>").replace(str(o), "<merged>")
        return {"offline_merge_success": False, "exit_code": p.returncode,
                "diagnostic_excerpt": cleaned.strip()[:350]}
    # Only report structural merged FDT size, never publish the raw image.
    merged = o.read_bytes()
    need(merged[:4] == b"\xd0\x0d\xfe\xed", "merge reported success but no FDT")
    return {"offline_merge_success": True,
            "merged_bytes": len(merged),
            "fdt_total_bytes": int.from_bytes(merged[4:8], "big")}


def audit(public_dtbo, public_boot_dtb, mainline_dtb, compatibility_dtb=None):
    entries, dtbo = parse_dtbo(public_dtbo.read_bytes())
    boot_sources = find_dtb_segments(public_boot_dtb.read_bytes())
    mainline = mainline_dtb.read_bytes()
    verify_dtb_identity(mainline)
    report = {
        "device": "umi",
        "phase": "P1p-bootloader-DTBO-overlay-compatibility-offline",
        "dtbo": dtbo,
        "boot_source": "public pinned LineageOS boot; not user's private KernelSU boot",
        "original_boot_dtb_fdt_count": len(boot_sources),
        "results": {},
        "device_boot_proven": False,
        "safe_to_flash": False,
        "all_tests_host_only": True
    }
    with tempfile.TemporaryDirectory(prefix="umi-dtbo-audit-") as temporary:
        work = Path(temporary)
        overlay = work / "vendor-umi-index11.dtbo"
        overlay.write_bytes(entries[EXPECTED_UMI_INDEX]["data"])
        for i, base in enumerate(boot_sources):
            report["results"][f"official_base_{i}"] = merge_probe(
                base, overlay, work, f"official_{i}")
        report["results"]["mainline_p1n"] = merge_probe(
            mainline, overlay, work, "mainline_p1n")
        if compatibility_dtb is not None:
            p1q = compatibility_dtb.read_bytes()
            need(p1q[:4] == b"\xd0\x0d\xfe\xed" and
                 b"Xiaomi Mi 10 (umi)" in p1q,
                 "P1q candidate DTB not recognized")
            report["results"]["mainline_p1q_abl_symbols"] = merge_probe(
                p1q, overlay, work, "mainline_p1q")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dtbo", type=Path, required=True)
    p.add_argument("--public-boot-dtb", type=Path, required=True)
    p.add_argument("--mainline-dtb", type=Path, required=True)
    p.add_argument("--compatibility-dtb", type=Path)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    try:
        report = audit(args.dtbo, args.public_boot_dtb, args.mainline_dtb,
                       args.compatibility_dtb)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n",
                               encoding="utf8")
        print(json.dumps(report, indent=2))
        # A failed merge is valid diagnostic evidence, not a CI infra failure.
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print("Offline DTBO audit failed closed: " + type(exc).__name__ +
              ": " + str(exc)[:180])
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
