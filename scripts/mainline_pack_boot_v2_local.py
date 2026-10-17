#!/usr/bin/env python3
"""Build a LOCAL experimental umi Android boot header v2 from private stock.

Uses *the user's actual backed-up boot.img*, pinned AOSP/Lineage mkbootimg tools,
Linux 6.12 ARM64 Image, RAM-only /init archive, and the umi P1n DTB. No ADB,
no flashing or partition writes. Fail closed on unfamiliar AVB/layout.
"""
import argparse
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inspect_stock_boot import audit_boot

MAX_BOOT = 134217728
MAX_INITRD = 8 * 1024 * 1024
CMD_ADD = "rdinit=/init loglevel=8 ignore_loglevel"

def need(ok, msg):
    if not ok:
        raise ValueError(msg)

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            data = f.read(1024 * 1024)
            if not data:
                break
            h.update(data)
    return h.hexdigest()

def validate_inputs(stock, preflight, kernel, ramdisk, dtb):
    p = json.loads(preflight.read_text(encoding="utf-8"))
    need(p.get("device") == "umi", "wrong preflight device")
    pb = p["backups"]["boot"]
    need(pb.get("saved_locally") and
         pb["size_bytes"] == MAX_BOOT and
         sha256(stock) == pb["sha256"],
         "private boot backup checksum does not match the verified preflight")
    info = audit_boot(stock)
    need(info["boot_header_version"] == 2 and
         info["page_size"] == 4096 and
         info["image_size_bytes"] == MAX_BOOT and
         info["sections"]["kernel"]["size"] == pb["header"]["kernel_bytes"] and
         info["sections"]["ramdisk"]["size"] == pb["header"]["ramdisk_bytes"] and
         info["layout_plausible_for_umi"],
         "unexpected stock Boot v2 layout")
    need(info["sections"]["dtb"]["size"] > 0,
         "stock boot v2 contains NO standalone DTB: appended DTB layout needs separate handling")
    need(0 < kernel.stat().st_size < 90 * 1024 * 1024,
         "kernel Image too large or empty")
    with kernel.open("rb") as f:
        f.seek(0x38)
        need(f.read(4) == b"ARMd", "not an uncompressed arm64 Linux Image")
    with dtb.open("rb") as f:
        head = f.read(64)
        f.seek(0, 2)
        size = f.tell()
        need(head[:4] == b"\xd0\x0d\xfe\xed" and size < 8 * 1024 * 1024,
             "not an FDT DTB")
        declared = int.from_bytes(head[4:8], "big")
        need(40 <= declared <= size, "invalid FDT DTB size")
    need(b"Xiaomi Mi 10 (umi)" in dtb.read_bytes()
         and b"ramoops@b0000000" in dtb.read_bytes(),
         "input DTB isn't the umi P1n test DTS")
    need(0 < ramdisk.stat().st_size <= MAX_INITRD,
         "ramdisk unexpectedly large or missing")
    with gzip.open(ramdisk, "rb") as f:
        archive = f.read(MAX_INITRD + 1)
    need(archive.startswith(b"070701") and len(archive) <= MAX_INITRD and
         b"UMI612-MINIMAL-INIT" in archive,
         "ramdisk isn't our static, RAM-only test initramfs")
    return info

def mkboot_args(unpack_tool, tools_dir, original, working):
    cmd = [sys.executable, str(unpack_tool),
           "--boot_img", str(original), "--out", str(working),
           "--format", "mkbootimg", "--null"]
    p = subprocess.run(cmd, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, check=True, timeout=180)
    raw = [os.fsdecode(x) for x in p.stdout.split(b"\0") if x]
    need(len(raw) >= 8 and len(raw) % 2 == 0, "unexpected mkbootimg arg-list shape")
    pairs = dict(zip(raw[::2], raw[1::2]))
    need(len(pairs) * 2 == len(raw), "duplicate mkbootimg argument")
    for required in ("--kernel", "--ramdisk", "--dtb", "--header_version",
                     "--pagesize"):
        need(required in pairs, "missing boot pack arg " + required)
    need(pairs["--header_version"] == "2" and int(pairs["--pagesize"], 0) == 4096,
         "unpack_bootimg changed header/page")
    return raw, pairs

def parse_avb_info(text):
    def get(field):
        match = re.search(r"^" + re.escape(field) + r":\s*(\S+)\s*$",
                          text, re.M)
        return match.group(1) if match else None
    need(get("Algorithm") == "NONE" and
         get("Hash Algorithm") == "sha256" and
         get("Partition Name") == "boot",
         "original AVB hash footer has unsupported algorithm/layout")
    props = []
    for line in text.splitlines():
        if line.strip().startswith("Prop:"):
            m = re.fullmatch(r"\s*Prop:\s*([^ ]+)\s*->\s*'(.*)'\s*", line)
            need(m is not None and len(m.group(1)) < 128 and
                 len(m.group(2)) <= 512 and "\0" not in m.group(2),
                 "unsupported original AVB property representation")
            props.append(m.group(1) + ":" + m.group(2))
    return props

def run_pack(stock, preflight, kernel, initramfs, dtb, mktools, avbtool, output):
    need(not output.exists(), "output already exists; refusing replacement")
    need(not output.resolve().is_relative_to(Path(__file__).resolve().parents[1]),
         "experiment boot must be outside Git checkout")
    need((mktools / "unpack_bootimg.py").is_file() and
         (mktools / "mkbootimg.py").is_file() and
         avbtool.is_file(), "mkbootimg/avbtool paths unavailable")
    stock_info = validate_inputs(stock, preflight, kernel, initramfs, dtb)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(output.parent), prefix=".umi-firstboot-") as d:
        tempdir = Path(d)
        args, pairs = mkboot_args(mktools / "unpack_bootimg.py",
                                  mktools, stock, tempdir / "unpacked")
        replace = {
            "--kernel": str(kernel.resolve()),
            "--ramdisk": str(initramfs.resolve()),
            "--dtb": str(dtb.resolve()),
        }
        oldline = pairs.get("--cmdline", "")
        # Legacy "skip_initramfs" is incompatible with a RAM-only /init test.
        need("skip_initramfs" not in oldline,
             "stock boot forces skip_initramfs: requires manual cmdline study")
        need(len(oldline) + len(CMD_ADD) < 1500,
             "cannot safely append Linux early-log options")
        if "--cmdline" in pairs:
            replace["--cmdline"] = (oldline + " " + CMD_ADD).strip()
        else:
            raise ValueError("original boot has no --cmdline args; refuse guessing")
        args = [replace.get(x, x) if i % 2 else x for i, x in enumerate(args)]
        draft = tempdir / "experiment-unsigned.img"
        subprocess.run([sys.executable, str(mktools / "mkbootimg.py"),
                        *args, "--output", str(draft)],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       check=True, timeout=180)
        need(draft.is_file() and draft.stat().st_size < MAX_BOOT,
             "mkbootimg emitted oversized or missing image")
        if stock_info["avb_footer_magic_at_file_end"]:
            p = subprocess.run([sys.executable, str(avbtool), "info_image",
                                "--image", str(stock)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, check=True, timeout=90)
            props = parse_avb_info(p.stdout)
            salt = sha256(kernel)
            avbargs = [sys.executable, str(avbtool), "add_hash_footer",
                       "--image", str(draft),
                       "--partition_size", str(MAX_BOOT),
                       "--partition_name", "boot",
                       "--algorithm", "NONE", "--hash_algorithm", "sha256",
                       "--salt", salt]
            for prop in props:
                avbargs.extend(("--prop", prop))
            subprocess.run(avbargs, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, check=True, timeout=180)
        new_info = audit_boot(draft)
        need(new_info["boot_header_version"] == 2 and
             new_info["page_size"] == stock_info["page_size"] and
             new_info["board_name"] == stock_info["board_name"] and
             new_info["os_version_packed"] == stock_info["os_version_packed"],
             "boot header fields changed unexpectedly")
        for key in ("kernel_addr", "ramdisk_addr", "second_addr",
                    "tags_addr", "dtb_addr"):
            need(new_info[key] == stock_info[key],
                 "boot header address changed: " + key)
        for field, path in (("kernel", kernel), ("ramdisk", initramfs),
                            ("dtb", dtb)):
            need(new_info["sections"][field]["sha256"] == sha256(path),
                 "repack section mismatch: " + field)
        need(new_info["image_size_bytes"] <= MAX_BOOT and
             (not stock_info["avb_footer_magic_at_file_end"]
              or new_info["avb_footer_magic_at_file_end"]) and
             CMD_ADD in new_info["cmdline"],
             "repack image/cmdline/footer invalid")
        os.replace(draft, output)
    return {"device": "umi", "phase": "LOCAL-test-only-boot-v2-repack",
            "output_filename": output.name,
            "output_bytes": output.stat().st_size,
            "output_sha256": sha256(output),
            "preserved_legacy_boot_addresses": True,
            "kernel_sha256": sha256(kernel),
            "ramdisk_sha256": sha256(initramfs),
            "dtb_sha256": sha256(dtb),
            "recovery_and_dtbo_partitions_unmodified": True,
            "phone_touched": False, "bootloader_dtbo_compat_verified": False,
            "recovery_adb_pstore_survival_verified": False,
            "mainline_runtime_tested": False, "safe_to_flash": False}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stock", required=True, type=Path)
    p.add_argument("--preflight", required=True, type=Path)
    p.add_argument("--kernel", required=True, type=Path)
    p.add_argument("--ramdisk", required=True, type=Path)
    p.add_argument("--dtb", required=True, type=Path)
    p.add_argument("--mkbootimg-dir", required=True, type=Path)
    p.add_argument("--avbtool", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    try:
        report = run_pack(a.stock, a.preflight, a.kernel, a.ramdisk,
                          a.dtb, a.mkbootimg_dir, a.avbtool, a.output)
        # No stock boot cmdline, fingerprint or original raw bytes printed.
        print(json.dumps(report, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError):
        print("Offline test image packaging refused/failed; "
              "no device contacted or modified.", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
