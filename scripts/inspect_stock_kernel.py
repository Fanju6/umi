#!/usr/bin/env python3
"""Offline forensic comparison: shipped umi boot kernel vs rebuilt config.

Never asserts bootability from matching configs. Does not modify any image.
"""
import argparse
import gzip
import json
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from inspect_stock_boot import audit_boot

MARKER_START = b"IKCFG_ST"
MARKER_END = b"IKCFG_ED"
INTERESTING = (
    "CONFIG_KSU", "CONFIG_LOCALVERSION", "CONFIG_LTO_CLANG",
    "CONFIG_CFI_CLANG", "CONFIG_CFI_PERMISSIVE",
    "CONFIG_ARM64", "CONFIG_ARM64_MODULE_PLTS", "CONFIG_RANDOMIZE_BASE",
    "CONFIG_SECURITY_SELINUX", "CONFIG_SECCOMP", "CONFIG_IKCONFIG",
    "CONFIG_MODULES", "CONFIG_MODULE_SIG", "CONFIG_STACKPROTECTOR",
    "CONFIG_KPROBES", "CONFIG_BPF_SYSCALL", "CONFIG_INITRAMFS_SOURCE",
)

def kernel_payload(boot_img: Path) -> bytes:
    layout = audit_boot(boot_img)
    s = layout["sections"]["kernel"]
    if s["size"] < 1024 or s["size"] > 128 * 1024 * 1024:
        raise ValueError("Unexpected stock kernel size")
    with boot_img.open("rb") as file:
        file.seek(s["offset"])
        payload = file.read(s["size"])
    if len(payload) != s["size"]:
        raise ValueError("Incomplete stock kernel")
    return payload


def config_from_image(image: bytes) -> dict[str, str] | None:
    start = image.find(MARKER_START)
    end = image.find(MARKER_END, start + len(MARKER_START))
    if start == -1 or end <= start:
        return None
    packed = image[start + len(MARKER_START):end]
    if len(packed) > 2 * 1024 * 1024:
        raise ValueError("Oversized IKCONFIG payload")
    raw = gzip.decompress(packed)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("Oversized decoded IKCONFIG")
    return parse_config(raw.decode("utf-8", "replace"))


def parse_config(raw: str) -> dict[str, str]:
    result = {}
    for line in raw.splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            k, v = line.split("=", 1)
            result[k] = v
        elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
            result[line[2:].split(" ", 1)[0]] = "n"
    return result


def inspect(image: bytes, generated_config: dict[str, str] | None = None) -> dict:
    stock_cfg = config_from_image(image)
    versions = re.findall(rb"Linux version [^\x00\r\n]{0,260}", image)
    version_strings = list(dict.fromkeys(
        v.decode("utf-8", "replace") for v in versions
    ))[:3]
    report = {
        "ikconfig_found": stock_cfg is not None,
        "stock_version_strings": version_strings,
        "stock_config_count": len(stock_cfg) if stock_cfg is not None else None,
        "stock_critical_config": {
            name: stock_cfg.get(name, "n") for name in INTERESTING
        } if stock_cfg is not None else None,
        "generated_critical_config": {
            name: generated_config.get(name, "n") for name in INTERESTING
        } if generated_config is not None else None,
        "config_diff_count": None,
        "config_diff_sample": [],
        "boot_failure_root_cause_proven": False,
        "safe_to_flash": False,
    }
    if stock_cfg is not None and generated_config is not None:
        keys = set(stock_cfg) | set(generated_config)
        differences = [
            {"config": k, "stock": stock_cfg.get(k, "n"), "experimental": generated_config.get(k, "n")}
            for k in sorted(keys) if stock_cfg.get(k, "n") != generated_config.get(k, "n")
        ]
        report["config_diff_count"] = len(differences)
        report["config_diff_sample"] = differences[:150]
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock_boot", type=Path)
    p.add_argument("--generated-config", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    config = None
    if args.generated_config:
        config = parse_config(args.generated_config.read_text(errors="replace"))
    report = inspect(kernel_payload(args.stock_boot), config)
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    print(output)
    return 0 if report["ikconfig_found"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
