#!/usr/bin/env python3
"""P1h: verify existing umi 4.19 pstore observations against pinned ramoops ABI.

Default offline only. --report reads a locally saved *sanitized P1g JSON*, not
the device or any pstore file. --upstream-* verifies pinned upstream sources.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "config/mainline-p1h-pstore-evidence.json"
P1G = ROOT / "config/mainline-p1g-recovery-gates.json"
UPSTREAM = "adc218676eef25575469234709c2d87185ca223a"
VENDOR = "71b13e62f057a649b77fe4062feb73ee72ad609c"
P1G_KEYS = {
    "schema_version", "stage", "device", "source", "observed_kernel",
    "non_ab_observed", "pstore_directory_present", "pstore_filesystem_mounted",
    "pstore_record_types_visible", "pstore_survives_crash_verified",
    "earlycon_verified", "recovery_path_tested", "safe_to_attempt_mainline_boot",
    "safe_to_flash", "writes_to_device", "note",
}
SAFETY_KEYS = {
    "safe_to_flash", "safe_to_attempt_mainline_boot", "known_good_recovery_verified",
    "pstore_crash_survival_verified", "uart_earlycon_verified",
    "ufs_parent_wiring_verified",
}

def require(value, message):
    if not value:
        raise ValueError(message)

def validate(graph, p1g):
    require((graph.get("schema_version"), graph.get("stage"), graph.get("device")) ==
            (1, "P1h", "umi"), "P1h identity drift")
    pins = {"vendor": VENDOR, "upstream": UPSTREAM}
    require(graph.get("locked") == p1g.get("locked") == pins, "pinned source mismatch")
    old_gates = p1g.get("gates", {})
    require(old_gates.get("safe_to_flash") is False and
            old_gates.get("safe_to_attempt_mainline_boot") is False,
            "P1g stage safety gate changed")
    e = graph.get("evidence", {})
    require(e.get("origin") == "user-shared P1g CLI summary" and
            e.get("full_local_p1g_json_inspected") is False and
            e.get("current_kernel_family") == "4.19", "evidence provenance promoted")
    require(e.get("pstore_directory_present") is True and
            e.get("pstore_filesystem_mounted") is True and
            e.get("record_classes_seen") == ["console", "pmsg"] and
            e.get("record_classes_not_seen") == ["dmesg", "ftrace"] and
            e.get("record_names_from_p1g_probe") == "*-ramoops",
            "P1g observed runtime summary drifted")
    unknowns = ("record_contents_inspected", "pstore_backend_name_confirmed_from_platform_device",
                "underlying_reserved_ram_physical_range_verified",
                "source_of_pstore_records_unequivocally_identified", "crash_survival_tested")
    require(all(e.get(k) is False for k in unknowns), "unverified runtime proof promoted")
    i = graph.get("interpretation", {})
    require(i == {"console_and_pmsg_are_distinct_buffers": True,
                  "absence_of_dmesg_file_proves_unsupported_backend": False,
                  "legacy_pstore_layout_safe_for_mainline": False,
                  "source_inspection_proves_umi_hardware": False},
            "pstore interpretation unsafe")
    mainline = graph.get("mainline_ramoops_requirements", {})
    require(mainline.get("binding") ==
            "Documentation/devicetree/bindings/reserved-memory/ramoops.yaml" and
            mainline.get("implementation") == "fs/pstore/ram.c" and
            mainline.get("requires_reserved_reg_and_compatible") is True and
            mainline.get("configuration_kinds") ==
            ["record-size", "console-size", "pmsg-size", "ftrace-size"] and
            mainline.get("umi_reserved_phandle") is None and
            mainline.get("umi_buffer_sizes") is None and
            mainline.get("mainline_612_boot_verified") is False,
            "unsupported 6.12 ramoops layout/size guess")
    gates = graph.get("gates", {})
    require(set(gates) == SAFETY_KEYS and all(gates[k] is False for k in gates),
            "unsafe boot or recovery gate")
    return {"stage": "P1h", "pstore_mounted_legacy_419": True,
            "record_classes_seen": ["console", "pmsg"],
            "record_classes_absent_in_snapshot": ["dmesg", "ftrace"],
            "pstore_crash_survival_proven": False, "mainline_memory_safe": False,
            "safe_to_flash": False}

def verify_local_p1g_report(report, graph):
    require(isinstance(report, dict) and set(report) == P1G_KEYS,
            "P1g report key whitelist mismatch")
    require(report["schema_version"] == 1 and report["stage"] == "P1g" and
            report["device"] == "umi" and
            report["source"] == "explicit non-root read-only adb shell",
            "P1g report identity invalid")
    require(isinstance(report["observed_kernel"], str) and
            re.fullmatch(r"4\.19\.[A-Za-z0-9._+~-]{1,125}", report["observed_kernel"]),
            "legacy 4.19 kernel not confirmed")
    require(report["non_ab_observed"] is True and
            report["pstore_directory_present"] is True and
            report["pstore_filesystem_mounted"] is True and
            report["pstore_record_types_visible"] == graph["evidence"]["record_classes_seen"],
            "local P1g report does not match shared summary")
    for key in ("pstore_survives_crash_verified", "earlycon_verified",
                "recovery_path_tested", "safe_to_attempt_mainline_boot",
                "safe_to_flash", "writes_to_device"):
        require(report[key] is False, "unsafe P1g report field: " + key)
    require(isinstance(report["note"], str) and
            report["note"] ==
            "mount/record presence is not evidence of retained crash logs or wired UART",
            "unexpected P1g report content")
    return True

def verify_upstream(ram, binding):
    for marker in (
        'module_param_named(console_size, ramoops_console_size',
        'module_param_named(pmsg_size, ramoops_pmsg_size',
        'parse_u32("record-size", pdata->record_size',
        'parse_u32("console-size", pdata->console_size',
        'parse_u32("pmsg-size", pdata->pmsg_size',
        '{ .compatible = "ramoops" }',
        'pstore_register(&cxt->pstore)',
    ):
        require(marker in ram, "pinned ramoops implementation drift: " + marker)
    for marker in (
        "const: ramoops", "record-size:", "console-size:", "pmsg-size:",
        "ftrace-size:", "max-reason:", "required:", "  - compatible", "  - reg",
    ):
        require(marker in binding, "pinned ramoops DT binding drift: " + marker)
    require("recovered after a reboot" in binding and
            "reserved-memory" in binding, "ramoops retention semantics not found")
    return True

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", type=Path, default=GRAPH)
    ap.add_argument("--p1g", type=Path, default=P1G)
    ap.add_argument("--report", type=Path,
                    help="user-owned sanitized P1g JSON on local computer; never uploaded")
    ap.add_argument("--upstream-ram", type=Path)
    ap.add_argument("--upstream-binding", type=Path)
    args = ap.parse_args()
    try:
        graph = json.loads(args.graph.read_text(encoding="utf-8"))
        p1g = json.loads(args.p1g.read_text(encoding="utf-8"))
        result = validate(graph, p1g)
        if args.report:
            report = json.loads(args.report.read_text(encoding="utf-8"))
            verify_local_p1g_report(report, graph)
        require((args.upstream_ram is None) == (args.upstream_binding is None),
                "must provide both pinned Linux 6.12 files")
        if args.upstream_ram:
            verify_upstream(args.upstream_ram.read_text(encoding="utf-8"),
                            args.upstream_binding.read_text(encoding="utf-8"))
        result["local_report_verified"] = bool(args.report)
        result["source_crosscheck"] = bool(args.upstream_ram)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
        print("P1h audit failed: " + str(e), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
