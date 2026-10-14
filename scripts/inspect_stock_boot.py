#!/usr/bin/env python3
"""Read-only Android boot.img (header v0-v2) audit, including LineageOS umi.

No image repacking, patching, flashing, or implicit "safe to flash" claims.
"""
import argparse
import hashlib
import json
import os
import struct
from pathlib import Path

MAGIC = b"ANDROID!"
HEADER_V0_SIZE = 1632
HEADER_V1_SIZE = 1648
HEADER_V2_SIZE = 1660
EXPECTED_UMI_PAGE_SIZE = 4096
# Source build limit, NOT a measured device partition capacity.
BOARD_UMI_BOOT_PARTITION_SIZE = 134217728


def u32(header: bytes, offset: int) -> int:
    return struct.unpack_from("<I", header, offset)[0]


def u64(header: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", header, offset)[0]


def align(value: int, page: int) -> int:
    return ((value + page - 1) // page) * page


def digest_range(f, offset: int, length: int) -> str:
    h = hashlib.sha256()
    f.seek(offset)
    remaining = length
    while remaining:
        block = f.read(min(1024 * 1024, remaining))
        if not block:
            raise ValueError("Unexpected EOF while hashing boot image section")
        h.update(block)
        remaining -= len(block)
    return h.hexdigest()


def audit_boot(path: Path) -> dict:
    size = path.stat().st_size
    if size < HEADER_V0_SIZE:
        raise ValueError("File too small to contain Android legacy boot header")
    with path.open("rb") as stream:
        header = stream.read(HEADER_V2_SIZE)
        if header[:8] != MAGIC:
            raise ValueError("Not an Android boot image (ANDROID! magic absent)")
        page = u32(header, 36)
        version = u32(header, 40)
        if page < 2048 or page > 65536 or page & (page - 1):
            raise ValueError("Invalid page_size in boot header")
        if version not in (0, 1, 2):
            raise ValueError("This safe audit supports Android boot header v0-v2 only")
        expected_header = (HEADER_V0_SIZE, HEADER_V1_SIZE, HEADER_V2_SIZE)[version]
        if len(header) < expected_header:
            raise ValueError("Truncated boot header")
        actual_header = (u32(header, 1644) if version >= 1 else HEADER_V0_SIZE)
        if actual_header != expected_header:
            raise ValueError("Unexpected header_size for this Android boot header version")
        kernel_size = u32(header, 8)
        ramdisk_size = u32(header, 16)
        second_size = u32(header, 24)
        recovery_dtbo_size = u32(header, 1632) if version >= 1 else 0
        recovery_dtbo_offset = u64(header, 1636) if version >= 1 else 0
        dtb_size = u32(header, 1648) if version >= 2 else 0
        dtb_addr = u64(header, 1652) if version >= 2 else 0
        sizes = (
            ("kernel", kernel_size),
            ("ramdisk", ramdisk_size),
            ("second", second_size),
            ("recovery_dtbo", recovery_dtbo_size),
            ("dtb", dtb_size),
        )
        cursor = page
        sections = {}
        for name, chunk_size in sizes:
            if name == "recovery_dtbo" and chunk_size and recovery_dtbo_offset:
                offset = recovery_dtbo_offset
            else:
                offset = cursor
            if chunk_size:
                if offset > size or chunk_size > size - offset:
                    raise ValueError("Truncated/out-of-range section: " + name)
                sections[name] = {
                    "offset": offset,
                    "size": chunk_size,
                    "sha256": digest_range(stream, offset, chunk_size),
                }
            else:
                sections[name] = {"offset": None, "size": 0, "sha256": None}
            if name == "recovery_dtbo" and chunk_size and recovery_dtbo_offset:
                cursor = max(cursor, align(offset + chunk_size, page))
            else:
                cursor += align(chunk_size, page)
        name = header[48:64].split(b"\0", 1)[0].decode("utf-8", "replace")
        cmdline = (header[64:576] + header[608:1632]).split(b"\0", 1)[0].decode("utf-8", "replace")
        stream.seek(max(0, size - 64))
        footer_bytes = stream.read(64)
        footer_magic = footer_bytes[:4] == b"AVBf"
        notes = []
        if page != EXPECTED_UMI_PAGE_SIZE:
            notes.append("Page size differs from the pinned umi BoardConfig.")
        if version != 2:
            notes.append("Boot header is not v2; do not assume legacy non-A/B pack args.")
        if size > BOARD_UMI_BOOT_PARTITION_SIZE:
            notes.append("Image exceeds stock BoardConfig's non-A/B boot limit.")
        if not ramdisk_size:
            notes.append("No embedded ramdisk: original boot packaging must be verified manually.")
        return {
            "path_name": path.name,
            "image_size_bytes": size,
            "image_sha256": digest_range(stream, 0, size),
            "boot_header_version": version,
            "header_size": actual_header,
            "page_size": page,
            "kernel_addr": u32(header, 12),
            "ramdisk_addr": u32(header, 20),
            "second_addr": u32(header, 28),
            "tags_addr": u32(header, 32),
            "dtb_addr": dtb_addr,
            "recovery_dtbo_offset": recovery_dtbo_offset,
            "board_name": name,
            "cmdline": cmdline,
            "os_version_packed": u32(header, 44),
            "sections": sections,
            "avb_footer_magic_at_file_end": footer_magic,
            "boardconfig_size_limit_bytes": BOARD_UMI_BOOT_PARTITION_SIZE,
            "layout_plausible_for_umi": (
                version == 2
                and page == EXPECTED_UMI_PAGE_SIZE
                and size <= BOARD_UMI_BOOT_PARTITION_SIZE
                and kernel_size > 0
                and ramdisk_size > 0
            ),
            "notes": notes,
            "boot_image_runtime_verified": False,
            "safe_to_flash": False,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("boot_image", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = audit_boot(args.boot_image)
    except (OSError, ValueError, struct.error) as exc:
        parser.exit(2, "Refusing unverified boot image: " + str(exc) + "\n")
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if not report["layout_plausible_for_umi"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
