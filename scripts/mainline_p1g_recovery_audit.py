#!/usr/bin/env python3
"""P1g read-only evidence gate for umi early logs and recovery readiness.

Offline default; optional pinned source cross-check. Does not run adb/fastboot.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "config/mainline-p1g-recovery-gates.json"
P1E = ROOT / "config/mainline-p1e-ufs-parent-graph.json"
OLD = "71b13e62f057a649b77fe4062feb73ee72ad609c"
NEW = "adc218676eef25575469234709c2d87185ca223a"
PARTITIONS = ["boot", "dtbo", "recovery", "super", "vbmeta"]
UARTS = ["qupv3_se12_2uart", "qupv3_se6_4uart"]
UNVERIFIED_BOOT = (
    "boot_header_image_parsed_in_this_stage", "bootloader_unlock_verified",
    "fastboot_boot_supported_verified", "recovery_boot_tested",
    "known_good_image_verified", "known_good_restore_tested",
)
UNVERIFIED_LOGS = (
    "uart_pad_mapping_confirmed", "uart_connector_confirmed",
    "xbl_log_proves_pstore", "upstream_sm8250_soc_has_explicit_ramoops",
    "usable_pstore_region_verified",
)
UNVERIFIED_GATES = (
    "recovery_boot_verified", "known_good_restoration_verified",
    "early_error_log_capture_verified", "mainline_ufs_pmics_ready",
    "final_dtbo_verified", "safe_to_attempt_mainline_boot", "safe_to_flash",
)

def need(value, why):
    if not value:
        raise ValueError(why)

def validate(g, p1e):
    need((g.get("schema_version"), g.get("stage"), g.get("device")) ==
         (1, "P1g", "umi"), "identity drift")
    pins = {"vendor": OLD, "upstream": NEW}
    need(g.get("locked") == p1e.get("locked") == pins, "pinned source mismatch")
    need(len(p1e.get("parent_inputs", [])) == 6 and
         all(x.get("umi_parent_phandle") is None for x in p1e["parent_inputs"]),
         "unverified PMIC parents changed")
    need(all(v is False for v in p1e.get("safety", {}).values()),
         "P1e safety regression")
    device = g.get("legacy_device_evidence", {})
    need(device.get("ab_update") is False and device.get("slot_suffix") is None,
         "non-A/B observation drift")
    need(device.get("partition_names_seen") == PARTITIONS and
         device.get("vendor_boot_partition_seen") is False,
         "observed partition set changed")
    need(device.get("boot_header_version_reported") == 2,
         "reported boot header changed without independent verification")
    need(all(device.get(k) is False for k in UNVERIFIED_BOOT),
         "unverified recovery capability promoted")
    need(set(device) == set(UNVERIFIED_BOOT) | {
         "ab_update", "slot_suffix", "partition_names_seen",
         "vendor_boot_partition_seen", "boot_header_version_reported"},
         "unexpected runtime/boot evidence")
    source = g.get("source_evidence", {})
    need(source.get("vendor_common_enabled_uarts") == UARTS and
         source.get("vendor_xbl_log_region") ==
         "res_xbl_uefi_log_region@80880000", "pinned UART/log source drift")
    need(all(source.get(k) is False for k in UNVERIFIED_LOGS),
         "unverified logging capability promoted")
    need(set(source) == set(UNVERIFIED_LOGS) | {
         "vendor_common_enabled_uarts", "vendor_xbl_log_region"},
         "unexpected source evidence")
    logs = g.get("runtime_logging", {})
    need(logs == {
        "pstore_mount_observed": None, "pstore_record_types_observed": None,
        "pstore_survived_reboot_or_crash_verified": False,
        "uart_earlycon_verified": False, "usb_early_boot_logs_verified": False,
    }, "untested logging evidence changed")
    gates = g.get("gates", {})
    need(gates.get("non_ab_partition_layout_supported") is True and
         all(gates.get(k) is False for k in UNVERIFIED_GATES) and
         set(gates) == set(UNVERIFIED_GATES) | {
             "non_ab_partition_layout_supported"},
         "unsafe recovery gate changed")
    return {"stage": "P1g", "non_ab_layout_supported": True,
            "early_logging_proven": False, "recovery_restoration_proven": False,
            "unknown_ufs_parent_groups": 6,
            "safe_to_attempt_mainline_boot": False, "safe_to_flash": False}

def verify_sources(g, old_common, old_kona, new_soc):
    for uart in UARTS:
        # Matches only the corresponding vendor source node, including explicit status.
        match = re.search(r"&" + uart +
                          r"\s*\{(?:(?!\n\};).)*?status\s*=\s*\"ok\"\s*;",
                          old_common, re.S)
        need(match is not None, "legacy UART enabled node missing: " + uart)
    need(re.search(r"res_xbl_uefi_log_region@80880000\s*\{", old_kona),
         "legacy XBL UEFI log reserved region missing")
    need(re.search(r"\bramoops\b", new_soc) is None,
         "upstream SoC acquired explicit ramoops; re-review required")
    return True

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", type=Path, default=GRAPH)
    ap.add_argument("--p1e", type=Path, default=P1E)
    ap.add_argument("--vendor-common", type=Path)
    ap.add_argument("--vendor-kona", type=Path)
    ap.add_argument("--mainline-soc", type=Path)
    a = ap.parse_args()
    try:
        g = json.loads(a.graph.read_text(encoding="utf-8"))
        p1e = json.loads(a.p1e.read_text(encoding="utf-8"))
        result = validate(g, p1e)
        files = (a.vendor_common, a.vendor_kona, a.mainline_soc)
        need(not any(files) or all(files), "must specify all three pinned source files")
        if all(files):
            verify_sources(g, *(f.read_text(encoding="utf-8") for f in files))
        result["pinned_source_crosscheck"] = all(files)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as ex:
        print("P1g audit failed: " + str(ex), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
