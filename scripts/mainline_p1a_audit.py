#!/usr/bin/env python3
"""P1a pinned upstream/vendor hardware mapping audit, without builds or flashing.

Accepts locally fetched reference files. Checks label presence, controller base,
legacy rail names and mainline reserved-memory consumers. Never enables devices.
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/mainline-p1a-dependencies.json"
BOARD = ROOT / "research/mainline/sm8250-xiaomi-umi-p1a.dts"
PINS = {
    "upstream": "adc218676eef25575469234709c2d87185ca223a",
    "downstream": "71b13e62f057a649b77fe4062feb73ee72ad609c",
}
CONSUMERS = {"smem_mem", "gpu_mem", "slpi_mem", "cdsp_mem", "video_mem", "adsp_mem"}
CONTROLLERS = {"ufs_mem_hc", "ufs_mem_phy", "usb_1",
               "usb_1_dwc3", "usb_1_hsphy", "usb_1_qmpphy"}


def check_manifest(m, board):
    if (m.get("schema_version"), m.get("stage"), m.get("device")) != (1, "P1a", "umi"):
        raise ValueError("invalid P1a target")
    if m.get("upstream", {}).get("sha") != PINS["upstream"]:
        raise ValueError("upstream SHA differs from verified baseline")
    if m.get("downstream", {}).get("sha") != PINS["downstream"]:
        raise ValueError("vendor SHA differs from verified baseline")
    if any(m.get("safety", {}).get(k) is not False for k in
           ("safe_to_flash", "boot_image_available", "ufs_enabled", "usb_enabled",
            "regulators_verified", "android_boot_verified")):
        raise ValueError("P1a safety gate may not be overridden")
    hardware = m.get("hardware", [])
    labels = {x.get("upstream_label") for x in hardware}
    if len(hardware) != 6 or labels != CONTROLLERS:
        raise ValueError("incomplete P1a source mapping")
    if set(m.get("upstream_memory_consumers", [])) != CONSUMERS:
        raise ValueError("upstream memory consumers must be audited")
    if '#include "sm8250-xiaomi-umi-p0c.dts"' not in board:
        raise ValueError("P1a must reuse the reviewed P0c board memory base")
    if "OFFLINE-ONLY" not in board or "NOT BOOTABLE" not in board:
        raise ValueError("P1a is missing research-only warnings")
    stripped = re.sub(r"/\*.*?\*/|//[^\n]*", "", board, flags=re.S)
    if re.search(r"\b(?:qcom,board-id|qcom,msm-id|bootargs)\s*=", stripped):
        raise ValueError("P1a may not set boot image identity")
    if re.search(r'status\s*=\s*"(?:okay|ok)"\s*;', stripped):
        raise ValueError("P1a may not enable any controller")
    for label in CONTROLLERS:
        match = re.search(r"&" + re.escape(label) +
                          r'\s*\{\s*status\s*=\s*"disabled"\s*;\s*\};', stripped)
        if not match:
            raise ValueError("P1a missing explicit disabled state: " + label)
    if re.search(r"\b(?:vcc|vccq|vdda-phy|vdda-pll|vbus)-supply\s*=", stripped):
        raise ValueError("P1a may not invent a PMIC supply wiring")


def check_source(m, upstream, vendors):
    needed = {x["vendor_file"] for x in m["hardware"]}
    if needed - set(vendors):
        raise ValueError("required pinned vendor DTS not available")
    for x in m["hardware"]:
        label = x["upstream_label"]
        match = re.search(r"\b" + re.escape(label) +
                          r"\s*:\s*[\w,@-]+\s*\{", upstream)
        if not match:
            raise ValueError("upstream SM8250 label missing: " + label)
        # Verify address in the local controller header, not anywhere in the SoC file.
        addr = x["address"].lower().replace("0x", "")
        local = upstream[match.end():match.end() + 450]
        if not re.search(r"\breg\s*=\s*<[^;]*?\b0x0*" +
                         re.escape(addr.lstrip("0")) + r"\b", local, re.I | re.S):
            raise ValueError("upstream controller reg mismatch: " + label)
        vendor = vendors[x["vendor_file"]]
        for needle in x["vendor_pins"]:
            if needle not in vendor:
                raise ValueError("vendor evidence changed: " + x["id"] + ": " + needle)
    found = set(re.findall(r"\bmemory-region\s*=\s*<\s*&([a-z0-9_]+)", upstream))
    if found != CONSUMERS:
        raise ValueError("memory-region consumers changed; manually review: " +
                         ",".join(sorted(found ^ CONSUMERS)))
    return {"source_pin_checked": True, "controller_count": len(m["hardware"]),
            "memory_region_consumers": sorted(found),
            "ufs_enabled": False, "usb_enabled": False,
            "safe_to_flash": False}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--board", type=Path, default=BOARD)
    ap.add_argument("--upstream", type=Path, help="pinned Linux v6.12 sm8250.dtsi")
    ap.add_argument("--vendor-root", type=Path, help="directory with pinned vendor .dtsi files")
    args = ap.parse_args()
    m = json.loads(args.manifest.read_text(encoding="utf-8"))
    board = args.board.read_text(encoding="utf-8")
    check_manifest(m, board)
    result = {"phase": "P1a", "manifest_passed": True,
              "source_checked": False, "bootable": False, "safe_to_flash": False}
    if (args.upstream is None) != (args.vendor_root is None):
        raise ValueError("both --upstream and --vendor-root are required for full source check")
    if args.upstream:
        upstream = args.upstream.read_text(encoding="utf-8")
        vendors = {
            name: (args.vendor_root / name).read_text(encoding="utf-8")
            for name in {x["vendor_file"] for x in m["hardware"]}
        }
        result.update(check_source(m, upstream, vendors))
        result["source_checked"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
