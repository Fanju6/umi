#!/usr/bin/env python3
"""Audit sanitized umi P1b legacy runtime supply evidence against 8 pinned DTS links.

This is offline. It neither reads physical devices nor writes regulator settings.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "config/mainline-p1b-power.json"
OBSERVED = ROOT / "config/mainline-p1b-observed.json"
IMPORTANT = {"pm8150_l2", "pm8150_l5", "pm8150_l6", "pm8150_l9",
             "pm8150_l12", "pm8150_l17", "pm8150_s4"}
FALSE_GATES = ("safe_to_flash", "ufs_enabled_on_linux612",
               "usb_enabled_on_linux612", "safe_board_voltage_ranges_verified",
               "rpmh_binding_verified", "typec_connector_graph_verified")


def valid_int(value):
    return type(value) is int and 0 < value < 10_000_000


def verify(snapshot, mapping):
    if snapshot.get("schema_version") != 1 or (snapshot.get("phase"), snapshot.get("device")) != ("P1b-live", "umi"):
        raise ValueError("invalid P1b umi snapshot")
    if snapshot.get("source", {}).get("kernel_family") != "Linux 4.19.325":
        raise ValueError("only observed legacy kernel evidence is supported")
    if snapshot.get("source", {}).get("regulator_entries_observed") != 56:
        raise ValueError("regulator sample count differs from actual P1b evidence")
    if any(snapshot.get("safety", {}).get(x) is not False for x in FALSE_GATES):
        raise ValueError("not allowed to mark mainline or voltage safety as verified")
    if (mapping.get("device"), mapping.get("phase")) != ("umi", "P1b"):
        raise ValueError("unrecognized static DTS mapping")
    expected = [x.get("legacy") for x in mapping.get("rails", [])]
    if len(expected) != 8 or set(expected) != IMPORTANT:
        raise ValueError("static UFS/USB supply map incomplete")
    rails = snapshot.get("rails", [])
    if len(rails) != 7 or len({x.get("name") for x in rails}) != 7 or {x.get("name") for x in rails} != IMPORTANT:
        raise ValueError("unexpected or missing physical supply rail")
    for rail in rails:
        name = rail["name"]
        if not re.fullmatch(r"pm8150_(?:l(?:2|5|6|9|12|17)|s4)", name):
            raise ValueError("virtual/_level rail is not a target supply: " + name)
        if rail.get("regulator_state") != "enabled" or rail.get("units") != "uV":
            raise ValueError("observed physical rail state/units invalid: " + name)
        current = rail.get("observed_microvolts")
        minimum = rail.get("reported_min_microvolts")
        maximum = rail.get("reported_max_microvolts")
        if not all(valid_int(x) for x in (current, minimum, maximum)) or not minimum <= current <= maximum:
            raise ValueError("impossible reported voltage snapshot: " + name)
    typec = snapshot.get("additional_observations", {}).get("typec", {})
    if typec.get("data_role") != "device" or typec.get("power_role") != "sink":
        raise ValueError("recorded Type-C snapshot does not match source")
    usb = snapshot["additional_observations"]["usb_power_supply"]
    if usb.get("reported_voltage_max_uv") != 5000000 or usb.get("reported_current_max_ua") != 1550000:
        raise ValueError("USB supply limits unexpectedly changed in derived snapshot")
    return {
        "stage": "P1b", "legacy_supplies_observed": len(rails),
        "legacy_dts_links_accounted": len(expected),
        "typec_observed": True, "voltage_is_safe_for_mainline": False,
        "mainline_regulator_binding_verified": False, "boot_image_available": False,
        "safe_to_flash": False,
    }


def compare_with_uncommitted_report(raw_report, snapshot):
    """Optional local consistency check; never saves/re-exports user's raw JSON."""
    if (raw_report.get("schema_version"), raw_report.get("phase"), raw_report.get("device")) != (1, "P1b", "umi"):
        raise ValueError("original user report has unexpected identity")
    if raw_report.get("writes_performed") is not False or raw_report.get("safe_to_flash") is not False:
        raise ValueError("not an unprivileged readonly user report")
    all_rails = raw_report.get("groups", {}).get("regulator", {})
    if raw_report.get("summary", {}).get("regulator") != 56 or len(all_rails) != 56:
        raise ValueError("original report regulator sample is incomplete")
    names = {}
    for item in all_rails.values():
        if "name" in item:
            if item["name"] in names:
                raise ValueError("duplicate regulator name in raw report")
            names[item["name"]] = item
    for rail in snapshot["rails"]:
        actual = names.get(rail["name"])
        if actual is None:
            raise ValueError("regulator missing in source report: " + rail["name"])
        for dst, src in (
            ("observed_microvolts", "microvolts"),
            ("reported_min_microvolts", "min_microvolts"),
            ("reported_max_microvolts", "max_microvolts"),
        ):
            if actual.get(src) != str(rail[dst]):
                raise ValueError("reported regulator value changed: " + rail["name"])
        if actual.get("state") != rail["regulator_state"]:
            raise ValueError("reported regulator state changed: " + rail["name"])
    usb = raw_report.get("groups", {}).get("usb_supply", {}).get("usb", {})
    if usb.get("type") != "USB_PD" or usb.get("online") != "1":
        raise ValueError("USB observation differs from snapshot")
    typec = raw_report.get("groups", {}).get("typec", {}).get("port0", {})
    if typec.get("data_role") != "host [device]" or typec.get("power_role") != "source [sink]":
        raise ValueError("Type-C snapshot roles differ from source report")
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot", type=Path, default=OBSERVED)
    p.add_argument("--matrix", type=Path, default=MATRIX)
    p.add_argument("--report", type=Path, help="optional LOCAL source report (never copied or committed)")
    args = p.parse_args()
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        mapping = json.loads(args.matrix.read_text(encoding="utf-8"))
        output = verify(snapshot, mapping)
        if args.report:
            raw_report = json.loads(args.report.read_text(encoding="utf-8"))
            compare_with_uncommitted_report(raw_report, snapshot)
            output["local_source_report_consistent"] = True
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"P1b observed evidence validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
