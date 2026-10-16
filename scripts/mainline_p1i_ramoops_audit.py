#!/usr/bin/env python3
"""P1i offline audit of P0c reserved-memory names and 4.19 Pstore evidence.

Optional --report reads a sanitized P1i file locally. No ADB invocation here.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "config/mainline-p1i-ramoops-registration.json"
P0C = ROOT / "config/mainline-umi-p0c-memory.json"
P1H = ROOT / "config/mainline-p1h-pstore-evidence.json"

REPORT_KEYS = {
    "schema_version", "phase", "device", "source", "legacy_kernel",
    "pstore_mounted", "ramoops_platform_device_name_observed",
    "ramoops_dt_compatible_candidate_observed",
    "ramoops_module_parameters_dir_present", "physical_address_read",
    "ram_contents_read", "pstore_log_contents_read", "physical_region_verified",
    "ramoops_backend_mapping_verified", "recovery_tested",
    "safe_to_attempt_mainline_boot", "safe_to_flash", "writes_to_device",
    "limitations",
}
FLAG_FALSE = (
    "memory_mapping_verified", "legacy_pstore_reuse_in_mainline_verified",
    "early_logging_reliability_verified", "recovery_path_verified",
    "ufs_pmics_verified", "safe_to_attempt_mainline_boot", "safe_to_flash",
)

def require(ok, why):
    if not ok:
        raise ValueError(why)

def validate(g, p0c, p1h):
    require((g.get("schema_version"), g.get("stage"), g.get("device")) ==
            (1, "P1i", "umi"), "identity changed")
    mem = p0c.get("regions", {})
    fixed, dynamic = mem.get("fixed", []), mem.get("dynamic", [])
    require(len(fixed) == 22 and len(dynamic) == 12,
            "P0c 34-node baseline changed")
    require(all(isinstance(x.get("node"), str) for x in fixed + dynamic),
            "invalid P0c node")
    # Name absence is intentionally NOT proof of absent platform-created ramoops.
    names = [x["node"] for x in fixed + dynamic]
    named = [n for n in names if re.match(r"^ramoops(?:@.*)?$", n)]
    require(len(named) == 0, "P0c now contains explicit ramoops: re-review")
    require(p0c.get("safety", {}).get("safe_to_flash") is False,
            "P0c safety unexpectedly relaxed")
    p1e = p1h.get("evidence", {})
    require(p1e.get("pstore_filesystem_mounted") is True and
            p1e.get("record_classes_seen") == ["console", "pmsg"] and
            p1h.get("gates", {}).get("safe_to_flash") is False,
            "P1h source evidence changed")
    e = g.get("evidence", {})
    require(e == {
        "source": "P0c 34-node running-device reserved-memory metadata + user P1h verified report summary",
        "legacy_419_pstore_mounted": True,
        "legacy_record_classes_seen": ["console", "pmsg"],
        "p0c_fixed_nodes_count": 22,
        "p0c_dynamic_nodes_count": 12,
        "p0c_named_ramoops_nodes": 0,
        "named_ramoops_absence_proves_no_backend": False,
        "pstore_file_name_proves_physical_layout": False,
        "physical_address": None,
        "physical_size": None,
        "backend_registration_method": None,
        "crash_retention_verified": False,
    }, "unverified Pstore address or backend promoted")
    probe = g.get("next_probe", {})
    require(probe == {
        "opt_in_required": True, "requires_root": False,
        "reads_pstore_contents": False, "reads_physical_region": False,
        "reads_dt_reg_values": False,
        "checks": ["platform_ramoops_device_name",
                   "ramoops_dt_compatible_candidate",
                   "ramoops_module_parameters_dir"],
        "observation_not_proof": True,
    }, "probe safety contract changed")
    gate = g.get("gates", {})
    require(set(gate) == set(FLAG_FALSE) and
            all(gate[k] is False for k in FLAG_FALSE),
            "unsafe P1i startup/recovery gate")
    return {"stage": "P1i", "p0c_nodes_reviewed": len(names),
            "p0c_named_ramoops": len(named),
            "legacy_pstore_mounted": True,
            "ramoops_backend_mapping_verified": False,
            "physical_address_verified": False,
            "safe_to_attempt_mainline_boot": False, "safe_to_flash": False}

def verify_report(report):
    require(isinstance(report, dict) and set(report) == REPORT_KEYS,
            "P1i report whitelist failure")
    require(report.get("schema_version") == 1 and
            report.get("phase") == "P1i" and report.get("device") == "umi" and
            report.get("source") == "non-root explicit read-only adb metadata",
            "invalid P1i device identity")
    require(isinstance(report.get("legacy_kernel"), str) and re.fullmatch(
        r"4\.19\.[0-9A-Za-z._+~-]{1,120}", report["legacy_kernel"]),
        "not original 4.19 baseline")
    for key in ("pstore_mounted", "ramoops_platform_device_name_observed",
                "ramoops_dt_compatible_candidate_observed",
                "ramoops_module_parameters_dir_present"):
        require(type(report.get(key)) is bool, "invalid probe observation: " + key)
    for key in ("physical_address_read", "ram_contents_read",
                "pstore_log_contents_read", "physical_region_verified",
                "ramoops_backend_mapping_verified", "recovery_tested",
                "safe_to_attempt_mainline_boot", "safe_to_flash",
                "writes_to_device"):
        require(report.get(key) is False, "unsafe claim: " + key)
    require(report.get("limitations") ==
            "Presence/absence in searched paths is NOT complete registration or physical-memory proof",
            "report limitations modified")
    return {
        "pstore_mounted": report["pstore_mounted"],
        "platform_device_name_seen": report["ramoops_platform_device_name_observed"],
        "dt_compatible_candidate_seen": report["ramoops_dt_compatible_candidate_observed"],
        "module_params_dir_seen": report["ramoops_module_parameters_dir_present"],
        "physical_address_verified": False, "safe_to_flash": False,
    }

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--graph", type=Path, default=GRAPH)
    p.add_argument("--p0c", type=Path, default=P0C)
    p.add_argument("--p1h", type=Path, default=P1H)
    p.add_argument("--report", type=Path, help="private local P1i sanitized JSON")
    a = p.parse_args()
    try:
        g = json.loads(a.graph.read_text(encoding="utf-8"))
        p0c = json.loads(a.p0c.read_text(encoding="utf-8"))
        p1h = json.loads(a.p1h.read_text(encoding="utf-8"))
        result = validate(g, p0c, p1h)
        if a.report is not None:
            result["runtime_probe_summary"] = verify_report(
                json.loads(a.report.read_text(encoding="utf-8")))
        result["local_report_verified"] = a.report is not None
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as ex:
        print("P1i offline audit failed: " + str(ex), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
