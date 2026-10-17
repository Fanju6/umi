#!/usr/bin/env python3
"""P1j: pin/check vendor 4.19 ramoops early_param + P0c physical ranges.

Default: offline only. --report: previously saved local, sanitized metadata.
--vendor-*: immutable source files for CI. Never invokes adb/fastboot.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mainline-p1j-ramoops-memory.json"
P0C = ROOT / "config/mainline-umi-p0c-memory.json"
P1I = ROOT / "config/mainline-p1i-ramoops-registration.json"
VENDOR = "71b13e62f057a649b77fe4062feb73ee72ad609c"
UPSTREAM = "adc218676eef25575469234709c2d87185ca223a"
BASE = 0xB0000000
SIZE = 4 * 1024 * 1024
PARAMS = ("mem_address", "mem_size", "console_size", "pmsg_size")
FALSE_GATES = (
    "verified_running_ramoops_base_and_size", "full_physical_memory_ownership_verified",
    "mainline_ramoops_reuse_safe", "crash_log_survival_verified",
    "recovery_path_verified", "ufs_power_ready",
    "safe_to_attempt_mainline_boot", "safe_to_flash",
)

def require(condition, message):
    if not condition:
        raise ValueError(message)

def overlaps(a_start, a_end, b_start, b_end):
    """Physical intervals are [start, end): adjacency is not overlap."""
    return a_start < b_end and b_start < a_end

def inspect(graph, p0c, p1i):
    require((graph.get("schema_version"), graph.get("stage"), graph.get("device")) ==
            (1, "P1j", "umi"), "P1j identity changed")
    require(graph.get("locked") == {"vendor": VENDOR, "upstream": UPSTREAM},
            "source SHA drift")
    require(p0c.get("device") == "umi" and
            p0c.get("safety", {}).get("safe_to_flash") is False,
            "P0c provenance/safety drift")
    require(p1i.get("device") == "umi" and
            p1i.get("gates", {}).get("safe_to_flash") is False,
            "P1i provenance/safety drift")
    evidence = graph.get("legacy_source_candidate", {})
    require(evidence == {
        "source": "vendor fs/pstore/ram.c and sm8250-common.config pinned SHA",
        "config_cmdline": "cgroup_disable=pressure ramoops_memreserve=4M",
        "early_param": "ramoops_memreserve",
        "source_physical_base": "0xB0000000",
        "source_size_bytes": SIZE,
        "source_end_exclusive": "0xB0400000",
        "source_console_bytes": SIZE // 2,
        "source_pmsg_bytes": SIZE // 2,
        "registered_platform_name": "ramoops",
        "source_method": "memblock_reserve plus platform_device_register",
        "actual_running_cmdline_verified": False,
        "actual_running_parameter_values_verified": False,
    }, "unconfirmed source address/size promoted")
    memory = p0c.get("regions", {})
    fixed = memory.get("fixed", [])
    dynamic = memory.get("dynamic", [])
    require(len(fixed) == 22 and len(dynamic) == 12,
            "P0c fixed/dynamic region counts drifted")
    conflicts = []
    for entry in fixed:
        start = int(entry["base"], 16)
        size = int(entry["size"], 16)
        require(size > 0, "invalid fixed reservation size")
        if overlaps(BASE, BASE + SIZE, start, start + size):
            conflicts.append(entry["node"])
    require(not conflicts, "SOURCE CANDIDATE OVERLAPS P0C FIXED MEMORY: " + ",".join(conflicts))
    require(any(entry["node"] == "disp_rdump_region@9c000000" and
                int(entry["base"], 16) == BASE + SIZE for entry in fixed),
            "display dump adjacency evidence changed")
    before = graph.get("p0c_overlap_check", {})
    require(before == {
        "source_candidate_overlaps_22_fixed_ranges": False,
        "adjacent_fixed_region": "disp_rdump_region@9c000000",
        "adjacent_fixed_region_base": "0xB0400000",
        "dynamic_pools_have_verified_physical_bases": False,
        "not_all_ram_owners_enumerated": True,
    }, "P0c partial memory map overclaimed")
    mainline = graph.get("mainline_diff", {})
    require(mainline == {
        "same_vendor_early_param_in_mainline_612": False,
        "same_vendor_hardcoded_base_in_mainline_612": False,
        "allow_direct_mainline_ramoops_dts_insertion": False,
        "linux_612_device_booted": False,
    }, "mainline 6.12 compatibility overclaimed")
    gates = graph.get("gates", {})
    require(set(gates) == set(FALSE_GATES) and
            all(gates[key] is False for key in FALSE_GATES),
            "unsafe startup/recovery gate")
    return {"stage": "P1j", "source_candidate_base": "0xB0000000",
            "source_candidate_size_bytes": SIZE,
            "source_candidate_end_exclusive": "0xB0400000",
            "p0c_fixed_regions": 22, "p0c_fixed_overlap_count": len(conflicts),
            "p0c_dynamic_ranges_unknown": 12,
            "live_module_parameter_values_verified": False,
            "safe_to_attempt_mainline_boot": False, "safe_to_flash": False}

def verify_sources(vendor_driver, vendor_config, upstream_driver):
    checks = (
        'ramoops_data.mem_address = 0xB0000000;',
        'ramoops_data.console_size = size / 2;',
        'ramoops_data.pmsg_size = size / 2;',
        'memblock_reserve(ramoops_data.mem_address, ramoops_data.mem_size);',
        'early_param("ramoops_memreserve", ramoops_memreserve);',
        'platform_device_register(&ramoops_dev)',
        'core_initcall(msm_register_ramoops_device);',
        'mem_address = pdata->mem_address;',
        'mem_size = pdata->mem_size;',
    )
    for token in checks:
        require(token in vendor_driver, "vendor 4.19 source drift: " + token)
    require('CONFIG_CMDLINE="cgroup_disable=pressure ramoops_memreserve=4M"' in
            vendor_config, "vendor 4.19 command line config drift")
    require('ramoops_memreserve' not in upstream_driver and
            'ramoops_data.mem_address = 0xB0000000;' not in upstream_driver,
            "Linux 6.12 acquired different ramoops path; re-review required")
    return True

def verify_report(report):
    from_types = ("mem_address", "mem_size", "console_size", "pmsg_size")
    expected_keys = {
        "schema_version", "phase", "device", "source", "legacy_kernel",
        "pstore_mounted", "platform_ramoops_observed",
        "module_parameter_values", "all_four_parameters_readable",
        "parameter_values_match_vendor_candidate", "reads_pstore_contents",
        "reads_physical_memory_contents", "writes_device", "safe_to_flash",
        "safe_to_attempt_mainline_boot", "limits",
    }
    require(type(report) is dict and set(report) == expected_keys,
            "non-whitelisted report keys")
    require(report.get("schema_version") == 1 and report.get("phase") == "P1j" and
            report.get("device") == "umi" and
            report.get("source") == "explicit non-root adb sysfs parameter metadata" and
            isinstance(report.get("legacy_kernel"), str) and
            re.fullmatch(r"4\.19\.[0-9A-Za-z._+~-]{1,120}",
                         report["legacy_kernel"]), "incorrect report identity")
    require(report["pstore_mounted"] is True and
            report["platform_ramoops_observed"] is True,
            "P1i observed platform/pstore changed")
    require(report["reads_pstore_contents"] is False and
            report["reads_physical_memory_contents"] is False and
            report["writes_device"] is False and
            report["safe_to_flash"] is False and
            report["safe_to_attempt_mainline_boot"] is False,
            "unsafe report assertion")
    require(report["limits"] ==
            "sysfs parameter metadata only; cannot prove mapping ownership or crash survival",
            "missing limitation")
    params = report["module_parameter_values"]
    require(type(params) is dict and set(params) == set(from_types),
            "invalid module parameter whitelist")
    for k, v in params.items():
        require(v is None or (type(v) is int and 0 <= v < (1 << 64)),
                "invalid module parameter: " + k)
    readable = all(params[k] is not None for k in from_types)
    matched = readable and params == {
        "mem_address": BASE, "mem_size": SIZE,
        "console_size": SIZE // 2, "pmsg_size": SIZE // 2}
    require(report["all_four_parameters_readable"] is readable and
            report["parameter_values_match_vendor_candidate"] is matched,
            "module parameter cross-check mismatch")
    return {"local_sysfs_values_readable": readable,
            "values_match_locked_vendor_source": matched,
            "physical_memory_ownership_verified": False,
            "safe_to_flash": False}

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", type=Path, default=CONFIG)
    ap.add_argument("--p0c", type=Path, default=P0C)
    ap.add_argument("--p1i", type=Path, default=P1I)
    ap.add_argument("--report", type=Path, help="private local sanitized P1j report")
    ap.add_argument("--vendor-driver", type=Path)
    ap.add_argument("--vendor-config", type=Path)
    ap.add_argument("--upstream-driver", type=Path)
    args = ap.parse_args()
    try:
        graph = json.loads(args.graph.read_text(encoding="utf-8"))
        p0c = json.loads(args.p0c.read_text(encoding="utf-8"))
        p1i = json.loads(args.p1i.read_text(encoding="utf-8"))
        output = inspect(graph, p0c, p1i)
        sources = (args.vendor_driver, args.vendor_config, args.upstream_driver)
        require(not any(sources) or all(sources), "all three pinned sources required")
        if all(sources):
            verify_sources(*(p.read_text(encoding="utf-8") for p in sources))
        output["source_crosscheck"] = bool(all(sources))
        if args.report:
            output["runtime_parameter_evidence"] = verify_report(
                json.loads(args.report.read_text(encoding="utf-8")))
            # Derived only from the user-provided local report, never the static graph.
            output["live_module_parameter_values_verified"] = (
                output["runtime_parameter_evidence"]["local_sysfs_values_readable"] and
                output["runtime_parameter_evidence"]["values_match_locked_vendor_source"])
        output["local_report_verified"] = args.report is not None
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as ex:
        print("P1j audit failed: " + str(ex), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
