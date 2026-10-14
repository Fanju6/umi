#!/usr/bin/env python3
"""Compare an experimental umi boot.img to matching stock boot.img.

All checks are offline/read-only. Passing does not imply bootability,
SELinux correctness or Root/Manager authorization.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inspect_stock_boot import audit_boot


def checksum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def inspect(stock: Path, experiment: Path, new_kernel: Path,
            stock_avb_info: Path, experiment_avb_info: Path) -> dict:
    original = audit_boot(stock)
    modified = audit_boot(experiment)
    avb_original = stock_avb_info.read_text(encoding="utf-8")
    avb_new = experiment_avb_info.read_text(encoding="utf-8")
    kernel_sha = checksum(new_kernel)
    checks = {
        "header_v2": original["boot_header_version"] == modified["boot_header_version"] == 2,
        "page_size_4096": original["page_size"] == modified["page_size"] == 4096,
        "size_not_exceeding_stock_partition": (
            modified["image_size_bytes"] <= 134217728
            and modified["image_size_bytes"] == original["image_size_bytes"]
        ),
        "boot_addresses_unchanged": all(
            original[k] == modified[k] for k in
            ("kernel_addr", "ramdisk_addr", "second_addr", "tags_addr", "dtb_addr")
        ),
        "cmdline_unchanged": original["cmdline"] == modified["cmdline"],
        "board_name_unchanged": original["board_name"] == modified["board_name"],
        "os_version_unchanged": original["os_version_packed"] == modified["os_version_packed"],
        "ramdisk_identical_sha256": (
            original["sections"]["ramdisk"]["size"] > 0
            and original["sections"]["ramdisk"]["sha256"]
            == modified["sections"]["ramdisk"]["sha256"]
        ),
        "dtb_identical_sha256": (
            original["sections"]["dtb"]["size"] > 0
            and original["sections"]["dtb"]["sha256"]
            == modified["sections"]["dtb"]["sha256"]
        ),
        "second_identical_sha256": (
            original["sections"]["second"]["sha256"]
            == modified["sections"]["second"]["sha256"]
        ),
        "recovery_dtbo_identical_sha256": (
            original["sections"]["recovery_dtbo"]["sha256"]
            == modified["sections"]["recovery_dtbo"]["sha256"]
        ),
        "kernel_matches_rebuilt_image": (
            modified["sections"]["kernel"]["size"] == new_kernel.stat().st_size
            and modified["sections"]["kernel"]["sha256"] == kernel_sha
        ),
        "kernel_different_from_stock": (
            original["sections"]["kernel"]["sha256"] != kernel_sha
        ),
        "stock_unsigned_avb_hash": (
            "Algorithm:                NONE" in avb_original
            and "Partition Name:        boot" in avb_original
            and "Hash Algorithm:        sha256" in avb_original
        ),
        "experimental_unsigned_avb_hash": (
            "Algorithm:                NONE" in avb_new
            and "Partition Name:        boot" in avb_new
            and "Hash Algorithm:        sha256" in avb_new
            and modified["avb_footer_magic_at_file_end"]
        ),
        "lineage_fingerprint_preserved": (
            "com.android.build.boot.fingerprint ->" in avb_original
            and next((line.strip() for line in avb_original.splitlines()
                      if "com.android.build.boot.fingerprint ->" in line), None)
            == next((line.strip() for line in avb_new.splitlines()
                      if "com.android.build.boot.fingerprint ->" in line), None)
        ),
        "lineage_os_version_preserved": (
            "com.android.build.boot.os_version ->" in avb_original
            and next((line.strip() for line in avb_original.splitlines()
                      if "com.android.build.boot.os_version ->" in line), None)
            == next((line.strip() for line in avb_new.splitlines()
                      if "com.android.build.boot.os_version ->" in line), None)
        ),
    }
    return {
        "repack_structurally_verified": all(checks.values()),
        "checks": checks,
        "stock_image_sha256": original["image_sha256"],
        "stock_kernel_sha256": original["sections"]["kernel"]["sha256"],
        "experimental_boot_sha256": modified["image_sha256"],
        "experimental_kernel_sha256": kernel_sha,
        "experimental_image_size_bytes": modified["image_size_bytes"],
        "original_ramdisk_sha256": original["sections"]["ramdisk"]["sha256"],
        "experimental_ramdisk_sha256": modified["sections"]["ramdisk"]["sha256"],
        "original_dtb_sha256": original["sections"]["dtb"]["sha256"],
        "experimental_dtb_sha256": modified["sections"]["dtb"]["sha256"],
        "experimental_only": True,
        "safe_to_flash": False,
        "runtime_validated": False,
        "note": (
            "Passing compares the serialized boot.img only. Actual kernel "
            "boot, SELinux, AVB policy and KernelSU Manager have NOT been "
            "tested. The unsigned AVB hash is not a trusted signature."
        ),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock", type=Path)
    p.add_argument("experiment", type=Path)
    p.add_argument("kernel", type=Path)
    p.add_argument("stock_avb_info", type=Path)
    p.add_argument("experimental_avb_info", type=Path)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    report = inspect(a.stock, a.experiment, a.kernel,
                     a.stock_avb_info, a.experimental_avb_info)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["repack_structurally_verified"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
