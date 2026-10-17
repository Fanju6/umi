#!/usr/bin/env python3
"""Cloud-only umi Linux 6.12 lab Boot v2 packer from PINNED PUBLIC ROM boot.

No phone contact. Pin is the existing repository's official LineageOS umi
20261004 boot, NOT the user's private current boot. Fail on unsupported layout.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inspect_stock_boot import audit_boot
from mainline_pack_boot_v2_local import (
    CMD_ADD, MAX_BOOT, MAX_INITRD, mkboot_args, parse_avb_info, replace_mkbootimg_values, sha256,
)

PUBLIC_ROM_SHA256 = "ce4a917a9233921b03e748b1fffc7b5ecea613c7ddf72208f26c77189f31a693"
RAM_ONLY_BOOTARGS = "rdinit=/init loglevel=8 ignore_loglevel earlycon keep_bootcon initcall_debug printk.time=1 log_buf_len=4M"
PRIVATE_DEVICE_SHA256 = "2bb0cabcd7bf996cc0053ce9f44248d1ec59c3b583b3259a0343f2ef6544c3b7"

def require(cond, message):
    if not cond:
        raise ValueError(message)

def validate_data(stock, kernel, initrd, dtb):
    require(sha256(stock) == PUBLIC_ROM_SHA256, "wrong pinned public umi boot image")
    orig = audit_boot(stock)
    require(orig["boot_header_version"] == 2 and orig["page_size"] == 4096,
            "expected Android boot header v2 with 4096B pages")
    require(0 < orig["sections"]["dtb"]["size"] <= 8 * 1024 * 1024,
            "official stock boot lacks supported separate DTB section")
    require(orig["sections"]["ramdisk"]["size"] > 0, "stock ramdisk missing")
    require(orig["image_size_bytes"] <= MAX_BOOT, "public boot exceeds umi partition")
    require(0 < kernel.stat().st_size < 96 * 1024 * 1024,
            "bad ARM64 Image size")
    with kernel.open("rb") as f:
        f.seek(0x38)
        require(f.read(4) == b"ARMd", "not uncompressed ARM64 Linux Image")
    require(0 < initrd.stat().st_size <= MAX_INITRD, "bad initramfs size")
    import gzip
    with gzip.open(initrd, "rb") as f:
        body = f.read(MAX_INITRD + 1)
    require(body.startswith(b"070701") and len(body) <= MAX_INITRD
            and b"UMI612-MINIMAL-INIT" in body,
            "not approved static RAM-only /init archive")
    d = dtb.read_bytes()
    require(40 <= len(d) < 8 * 1024 * 1024
            and d[:4] == bytes.fromhex("d00dfeed")
            and 40 <= int.from_bytes(d[4:8], "big") <= len(d)
            and b"Xiaomi Mi 10 (umi) - P1p early diagnostic lab" in d
            and b"ramoops@b0000000" in d,
            "not approved umi P1n DTB")
    return orig

def run(stock, kernel, initrd, dtb, mktools, avbtool, output, report):
    require(not output.exists() and not report.exists(),
            "output already exists: refusing overwrite")
    require(output.resolve() != stock.resolve(), "cannot overwrite original boot")
    require((mktools / "unpack_bootimg.py").is_file() and
            (mktools / "mkbootimg.py").is_file() and avbtool.is_file(),
            "missing pinned mkbootimg/avbtool files")
    original = validate_data(stock, kernel, initrd, dtb)
    require(original["avb_footer_magic_at_file_end"],
            "public baseline missing expected AVB footer")
    output.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    with tempfile.TemporaryDirectory(prefix=".umi612-cloud-", dir=output.parent) as tmp:
        work = Path(tmp)
        raw_args, pairs = mkboot_args(
            mktools / "unpack_bootimg.py", mktools, stock, work / "unpacked")
        # This is NOT Android. Do not append to the long stock Android
        # cmdline (which may be split/truncated between v2 header fields).
        # Use a short, explicit, reproducible kernel-only command line.
        require("--cmdline" in pairs, "stock boot lacks a cmdline field")
        replacements = {
            "--kernel": str(kernel.resolve()),
            "--ramdisk": str(initrd.resolve()),
            "--dtb": str(dtb.resolve()),
            "--cmdline": RAM_ONLY_BOOTARGS,
        }
        args = replace_mkbootimg_values(raw_args, replacements)
        candidate = work / "umi612-cloud-experimental.img"
        subprocess.run([sys.executable, str(mktools / "mkbootimg.py"), *args,
                        "--output", str(candidate)],
                       check=True, capture_output=True, timeout=180)
        require(candidate.is_file() and 0 < candidate.stat().st_size < MAX_BOOT,
                "missing/oversized raw Android boot")
        avb_info = subprocess.run([sys.executable, str(avbtool), "info_image",
                                   "--image", str(stock)], check=True,
                                  capture_output=True, text=True, timeout=90)
        props = parse_avb_info(avb_info.stdout)
        require(any(p.startswith("com.android.build.boot.fingerprint:") for p in props),
                "expected pinned LineageOS boot fingerprint missing")
        require(any(p.startswith("com.android.build.boot.os_version:") for p in props),
                "expected pinned LineageOS OS version missing")
        command = [
            sys.executable, str(avbtool), "add_hash_footer",
            "--image", str(candidate), "--partition_size", str(MAX_BOOT),
            "--partition_name", "boot", "--algorithm", "NONE",
            "--hash_algorithm", "sha256", "--salt", sha256(kernel),
        ]
        for p in props:
            command += ["--prop", p]
        subprocess.run(command, check=True, capture_output=True, timeout=180)
        new = audit_boot(candidate)
        # Distinguish actual structural regressions from lossy mkbootimg
        # header reserialization; report just field names, never cmdline data.
        checks = {
            "header_version_v2": new["boot_header_version"] == 2,
            "page_size": new["page_size"] == original["page_size"],
            "partition_capacity": new["image_size_bytes"] <= MAX_BOOT,
            "avb_footer": bool(new["avb_footer_magic_at_file_end"]),
            "ramonly_cmdline": new["cmdline"] == RAM_ONLY_BOOTARGS,
            "board_name": new["board_name"] == original["board_name"],
            "os_version_packed": new["os_version_packed"] == original["os_version_packed"],
        }
        require(all(checks.values()), "repacked boot validation failed: " +
                ", ".join(key for key, ok in checks.items() if not ok))
        for field in ("kernel_addr", "ramdisk_addr", "second_addr",
                      "tags_addr", "dtb_addr"):
            require(new[field] == original[field],
                    "boot loader address mismatch: " + field)
        for field, file in (("kernel", kernel), ("ramdisk", initrd), ("dtb", dtb)):
            require(new["sections"][field]["sha256"] == sha256(file),
                    "repack payload SHA differs: " + field)
        info_new = subprocess.run([sys.executable, str(avbtool), "info_image",
                                   "--image", str(candidate)], check=True,
                                  capture_output=True, text=True, timeout=90)
        new_props = parse_avb_info(info_new.stdout)
        require(new_props == props, "AVB properties not preserved")
        os.replace(candidate, output)

    result = {
        "device": "umi",
        "purpose": "P1p Linux 6.12 RAM-only early diagnostics experiment",
        "baseline_rom": "LineageOS 23.2 2026-10-04 umi official public boot",
        "baseline_sha256": PUBLIC_ROM_SHA256,
        "actual_user_device_boot_sha256": PRIVATE_DEVICE_SHA256,
        "baseline_matches_user_current_boot": False,
        "difference_disclosed": True,
        "image_file": output.name,
        "image_bytes": output.stat().st_size,
        "image_sha256": sha256(output),
        "kernel_sha256": sha256(kernel),
        "ramdisk_sha256": sha256(initrd),
        "dtb_sha256": sha256(dtb),
        "header_v2_payload_and_avb_verified": True,
        "bootloader_dtb_compat_verified": False,
        "recovery_reflash_verified": False,
        "device_boot_tested": False,
        "safe_to_flash": False,
        "no_phone_contact_or_partition_writes": True,
    }
    report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("stock", "kernel", "ramdisk", "dtb", "mkbootimg-dir",
                 "avbtool", "output", "report"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    try:
        r = run(a.stock, a.kernel, a.ramdisk, a.dtb,
                getattr(a, "mkbootimg_dir"), a.avbtool, a.output, a.report)
        print(json.dumps(r, indent=2))
        return 0
    except ValueError as exc:
        # Inputs are pinned public ROM and build artifacts, not private data.
        # Print the specific guard that refused the image, to unblock CI triage.
        print("Cloud boot validation refused: " + str(exc), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        step = Path(str(exc.cmd[1])).name if isinstance(exc.cmd, list) and len(exc.cmd) > 1 else "tool"
        print("Cloud boot tool failed: " + step + " (exit " + str(exc.returncode) + ")", file=sys.stderr)
        return 1
    except (OSError, subprocess.SubprocessError, EOFError) as exc:
        print("Cloud boot packaging failed closed: " + type(exc).__name__, file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
