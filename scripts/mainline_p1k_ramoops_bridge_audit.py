#!/usr/bin/env python3
"""P1k: attest observed 4.19 sysfs ramoops values, fence mainline 6.12 reuse.

Offline by default. --report optionally reads a local sanitized P1j report;
never contacts ADB, reads logs, or creates DTS/boot artifacts.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import mainline_p1j_ramoops_memory_audit as p1j

GRAPH = ROOT / "config/mainline-p1k-ramoops-migration-evidence.json"
P0C = ROOT / "config/mainline-umi-p0c-memory.json"
P1J = ROOT / "config/mainline-p1j-ramoops-memory.json"

SOURCE_BASE = 0xB0000000
SOURCE_SIZE = 4 * 1024 * 1024
PARAMS = {
    "mem_address": SOURCE_BASE, "mem_size": SOURCE_SIZE,
    "console_size": 2 * 1024 * 1024, "pmsg_size": 2 * 1024 * 1024,
}

def require(ok, why):
    if not ok:
        raise ValueError(why)

def check(graph, p0c, j):
    require((graph.get("schema_version"), graph.get("stage"),
             graph.get("device")) == (1, "P1k", "umi"), "P1k identity drift")
    require(graph.get("locked") == j.get("locked") == {
        "vendor": p1j.VENDOR, "upstream": p1j.UPSTREAM},
        "locked sources changed")
    require(j.get("gates", {}).get("safe_to_flash") is False and
            j.get("gates", {}).get("safe_to_attempt_mainline_boot") is False,
            "P1j startup safety changed")
    ev = graph.get("runtime_evidence")
    require(ev == {
        "origin": "user-shared sanitized P1j CLI output with local_report_verified true",
        "local_user_report_validated": True,
        "raw_p1j_file_inspected_by_assistant": False,
        "legacy_kernel_family": "4.19",
        "sysfs_four_parameters_readable": True,
        "sysfs_four_parameters_match_vendor": True,
        "observed_parameters": PARAMS,
        "source_memory_range_end_exclusive": "0xB0400000",
        "verified_reported_parameter_values": True,
        "actual_physical_ram_owner_proven": False,
    }, "runtime provenance or observation promoted without evidence")
    mem = p0c.get("regions", {})
    fixed, dynamic = mem.get("fixed", []), mem.get("dynamic", [])
    require(len(fixed) == 22 and len(dynamic) == 12,
            "P0c region list changed")
    start, end = SOURCE_BASE, SOURCE_BASE + SOURCE_SIZE
    hits = [x["node"] for x in fixed if p1j.overlaps(
        start, end, int(x["base"], 16),
        int(x["base"], 16) + int(x["size"], 16))]
    require(not hits, "P1k candidate collides with P0c: " + ",".join(hits))
    require(any(x["node"] == "disp_rdump_region@9c000000" and
                int(x["base"], 16) == end for x in fixed),
            "display dump boundary changed")
    audit = graph.get("fixed_memory_audit")
    require(audit == {
        "p0c_fixed_regions_count": 22, "p0c_fixed_overlap_count": 0,
        "p0c_dynamic_regions_count": 12,
        "p0c_dynamic_actual_locations_verified": False,
        "non_dt_memory_owners_completely_known": False,
        "adjacent_reserved_region_name": "disp_rdump_region@9c000000",
        "adjacent_region_start": "0xB0400000",
    }, "incomplete memory map treated as complete")
    mainline = graph.get("mainline_612_migration")
    require(mainline == {
        "vendor_early_param_supported_as_is": False,
        "driver": "fs/pstore/ram.c",
        "binding": "Documentation/devicetree/bindings/reserved-memory/ramoops.yaml",
        "candidate_reserved_memory_resource_registered": False,
        "ramoops_dts_node_added": False,
        "ready_to_enable_ramoops": False,
        "ramoops_crash_retention_tested": False,
        "android_612_boot_tested": False,
    }, "unverified 6.12 integration claimed")
    gate = graph.get("gates")
    require(gate == {
        "runtime_metadata_matches_4_19_source": True,
        "complete_physical_memory_ownership_verified": False,
        "safe_to_copy_4_19_ram_region_to_612": False,
        "recovery_and_earlycon_proven": False,
        "ufs_parent_and_power_verified": False,
        "safe_to_attempt_mainline_boot": False,
        "safe_to_flash": False,
    }, "unsafe P1k gate")
    return {
        "stage": "P1k",
        "user_shared_runtime_params_match_vendor_source": True,
        "address": "0xB0000000", "size_bytes": SOURCE_SIZE,
        "p0c_fixed_overlap_count": 0, "p0c_dynamic_locations_unknown": 12,
        "mainline_ram_resource_defined": False,
        "complete_physical_ownership_verified": False,
        "safe_to_attempt_mainline_boot": False, "safe_to_flash": False,
    }

def check_mainline_source(driver, schema):
    for marker in (
        "static int ramoops_parse_dt(struct platform_device *pdev,",
        "platform_get_resource(pdev, IORESOURCE_MEM, 0)",
        "pdata->mem_size = resource_size(res);",
        "pdata->mem_address = res->start;",
        'parse_u32("record-size", pdata->record_size, 0);',
        'parse_u32("console-size", pdata->console_size, 0);',
        'parse_u32("pmsg-size", pdata->pmsg_size, 0);',
    ):
        require(marker in driver, "locked Linux 6.12 driver drift: " + marker)
    require("ramoops_memreserve" not in driver,
            "Linux 6.12 vendor parameter assumption changed")
    for marker in ("const: ramoops", "  - reg", "  - compatible",
                   "record-size:", "console-size:", "pmsg-size:"):
        require(marker in schema, "locked Linux 6.12 binding drift: " + marker)
    require("recovered after a reboot" in schema and
            "reserved-memory" in schema, "binding semantics drift")
    return True

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", type=Path, help="locally saved sanitized P1j JSON")
    ap.add_argument("--mainline-driver", type=Path, help="locked v6.12 fs/pstore/ram.c")
    ap.add_argument("--mainline-binding", type=Path, help="locked ramoops.yaml")
    a = ap.parse_args()
    try:
        g = json.loads(GRAPH.read_text(encoding="utf-8"))
        p0c = json.loads(P0C.read_text(encoding="utf-8"))
        j = json.loads(P1J.read_text(encoding="utf-8"))
        result = check(g, p0c, j)
        require((a.mainline_driver is None) == (a.mainline_binding is None),
                "both locked upstream source files are required together")
        if a.mainline_driver:
            check_mainline_source(a.mainline_driver.read_text(encoding="utf-8"),
                                  a.mainline_binding.read_text(encoding="utf-8"))
        result["pinned_mainline_source_crosscheck"] = bool(a.mainline_driver)
        if a.report:
            report = json.loads(a.report.read_text(encoding="utf-8"))
            attestation = p1j.verify_report(report)
            require(attestation["local_sysfs_values_readable"] is True and
                    attestation["values_match_locked_vendor_source"] is True,
                    "local P1j report does not attest four source parameters")
            require(report["module_parameter_values"] == PARAMS,
                    "report values differ from user-shared runtime evidence")
            result["local_report_verified"] = True
            result["runtime_metadata_match"] = True
        else:
            result["local_report_verified"] = False
            result["runtime_metadata_match"] = None
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as e:
        print("P1k audit failed: " + str(e), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
