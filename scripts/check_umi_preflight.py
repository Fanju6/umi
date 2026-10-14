#!/usr/bin/env python3
"""Verify the known umi device preflight against pinned source and boot layout.

No device access, firmware flashing or image construction. This only checks
reported observations; success MUST NOT be interpreted as safe to flash.
"""
import argparse
import json
from pathlib import Path


def pinned_kernel_sha(env_file: Path) -> str:
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("LINEAGE_KERNEL_SHA="):
            sha = line.split("=", 1)[1].strip()
            if len(sha) == 40 and all(c in "0123456789abcdef" for c in sha):
                return sha
            break
    raise ValueError("Invalid or missing pinned kernel SHA")


def inspect(profile: dict, kernel_sha: str) -> dict:
    parts = set(profile.get("partition_names", []))
    required = {"boot", "recovery", "dtbo", "vbmeta"}
    checks = {
        "target_umi": profile.get("device") == "umi",
        "android_api_36": profile.get("android_api") == 36,
        "lineage_23_2": str(profile.get("lineage_version", "")).startswith("23.2-"),
        "pinned_kernel_sha": ("g" + kernel_sha[:12]) in str(profile.get("kernel_release", "")),
        "selinux_enforcing": profile.get("selinux") == "Enforcing",
        "no_ab_updater": profile.get("ab_update") == "false",
        "no_slot": profile.get("boot_slot_suffix") == "" and profile.get("boot_slot") == "",
        "legacy_partition_names": required.issubset(parts),
        "no_slot_suffix_partitions": not any(
            name.endswith("_a") or name.endswith("_b") for name in parts
        ),
        "no_vendor_boot_or_init_boot": "vendor_boot" not in parts and "init_boot" not in parts,
    }
    return {
        "device_profile_match": all(checks.values()),
        "layout": "legacy_non_ab" if all(
            checks[k] for k in (
                "no_ab_updater", "no_slot", "legacy_partition_names",
                "no_slot_suffix_partitions", "no_vendor_boot_or_init_boot"
            )
        ) else "unconfirmed",
        "checks": checks,
        "verified_boot_state_observed": profile.get("verified_boot"),
        "safe_to_flash": False,
        "message": (
            "This confirms only the reported device/layout/source evidence. "
            "The actual boot.img header, ramdisk, AVB, recovery path, and "
            "KernelSU runtime/SELinux/Manager behavior remain unverified."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--source-env", type=Path,
                        default=Path(__file__).resolve().parents[1] / "config/upstream.env")
    args = parser.parse_args()
    report = inspect(
        json.loads(args.profile.read_text(encoding="utf-8")),
        pinned_kernel_sha(args.source_env),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["device_profile_match"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
