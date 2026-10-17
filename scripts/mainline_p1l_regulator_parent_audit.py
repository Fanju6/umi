#!/usr/bin/env python3
"""P1l: explicit distinction between RPMh DT schema validity and board wiring.

Never connects to hardware or edits a DTS. Optional --driver/--binding read only
locked upstream Linux 6.12 source files already downloaded for CI.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "config/mainline-p1l-regulator-parent-gates.json"
P1D = ROOT / "config/mainline-p1d-rpmh-evidence.json"
P1E = ROOT / "config/mainline-p1e-ufs-parent-graph.json"
P1F = ROOT / "config/mainline-p1f-ufs-lifecycle.json"
P1A_DTS = ROOT / "research/mainline/sm8250-xiaomi-umi-p1a.dts"
P1C_DTS = ROOT / "research/mainline/sm8250-xiaomi-umi-p1c.dts"
VENDOR = "71b13e62f057a649b77fe4062feb73ee72ad609c"
UPSTREAM = "adc218676eef25575469234709c2d87185ca223a"

GROUPS = {
    "vdd-s4-supply": (("pm8150_s4",), ("smps4",)),
    "vdd-l2-l10-supply": (("pm8150_l2",), ("ldo2",)),
    "vdd-l3-l4-l5-l18-supply": (("pm8150_l5",), ("ldo5",)),
    "vdd-l6-l9-supply": (("pm8150_l6", "pm8150_l9"), ("ldo6", "ldo9")),
    "vdd-l7-l12-l14-l15-supply": (("pm8150_l12",), ("ldo12",)),
    "vdd-l13-l16-l17-supply": (("pm8150_l17",), ("ldo17",)),
}
VOTES = {
    "qcom,vddp-ref-clk-supply": "pm8150_l6",
    "qcom,vccq-parent-supply": "pm8150a_s8",
}
DTS_DISABLED = ("ufs_mem_hc", "ufs_mem_phy", "usb_1", "usb_1_dwc3",
                "usb_1_hsphy", "usb_1_qmpphy")

def require(ok, reason):
    if not ok:
        raise ValueError(reason)

def validate(g, d, e, f, dts_a, dts_c):
    require((g.get("schema_version"), g.get("stage"), g.get("device")) ==
            (1, "P1l", "umi"), "P1l identity drift")
    pins = {"vendor": VENDOR, "upstream": UPSTREAM}
    require(g.get("locked") == d.get("locked") == e.get("locked") == f.get("locked") == pins,
            "fixed SHA drift")
    binding = g.get("binding", {})
    require(binding == {
        "path": "Documentation/devicetree/bindings/regulator/qcom,rpmh-regulator.yaml",
        "required_properties": ["compatible", "qcom,pmic-id"],
        "listed_parent_properties_are_top_level_required": False,
        "parent_properties_schema_allowed": True,
        "schema_acceptance_proves_wiring": False,
    }, "binding optional versus electrical wiring conflated")
    drv = g.get("driver", {})
    require(drv == {
        "path": "drivers/regulator/qcom-rpmh-regulator.c",
        "regulator_descriptor_uses_supply_name": True,
        "resource_lookup_uses_cmd_db": True,
        "mainline_hardware_probe_verified": False,
    }, "driver mapping overclaimed")
    gs = g.get("parent_groups", [])
    require(len(gs) == 6 and {x.get("property") for x in gs} == set(GROUPS),
            "six supply groups changed")
    previous = {r["property"] for r in e["parent_inputs"]}
    require(previous == set(GROUPS) and
            all(x["umi_parent_phandle"] is None for x in e["parent_inputs"]),
            "P1e board parent graph changed")
    parent_by_rail = {r["legacy"]: (r["parent_property"], r["mainline_child"])
                      for r in d["rails"]}
    require(len(parent_by_rail) == 7, "P1d seven UFS/USB rails changed")
    observed = set()
    for row in gs:
        prop = row["property"]
        rails, children = GROUPS[prop]
        require(row == {
            "property": prop, "legacy_rails": list(rails),
            "consumer_ids": list(children), "umi_parent_phandle": None,
        }, "unsupported umi parent phandle or supply group edit: " + prop)
        for legacy, child in zip(rails, children):
            require(parent_by_rail.get(legacy) == (prop, child),
                    "P1d mapping contradicts P1l: " + legacy)
            observed.add(legacy)
    require(observed == set(parent_by_rail), "P1d rails missing or duplicated")
    votes = g.get("vendor_only_votes", [])
    require(len(votes) == 2 and
            {v.get("property"): v.get("legacy_rail") for v in votes} == VOTES and
            all(v.get("mainline_replacement") is None for v in votes),
            "unsupported legacy vote replacement")
    require({v["property"]: v["source"] for v in f["votes"]} == VOTES,
            "P1f vendor UFS vote mismatch")
    require(g.get("confidence") == {
        "vendor_4_19_rail_resource_ids_source_verified": True,
        "mainline_612_supply_group_names_source_verified": True,
        "actual_umi_board_parent_phandles_verified": False,
        "real_ufs_power_sequence_verified": False,
        "mainline_pmic_probed": False,
    }, "unverified power evidence promoted")
    require(g.get("safety") == {
        "research_only": True,
        "mainline_regulator_providers_enabled": False,
        "mainline_ufs_enabled": False, "mainline_usb_enabled": False,
        "voltage_guessed": False, "parent_phandles_guessed": False,
        "boot_image_created": False, "safe_to_attempt_mainline_boot": False,
        "safe_to_flash": False,
    }, "unsafe P1l hardware gate")
    for name in DTS_DISABLED:
        expr = r"&" + name + r"\s*\{\s*status\s*=\s*\"disabled\";\s*\};"
        require(re.search(expr, dts_a), "P1a hardware node enabled: " + name)
    require(re.search(r"regulators-umi-reference\s*\{[^{}]*status\s*=\s*\"disabled\";",
                      dts_c, re.S), "P1c regulator provider no longer disabled")
    return {
        "stage": "P1l", "parent_supply_property_groups": 6,
        "old_regulator_outputs_grouped": 7,
        "unmapped_vendor_ufs_votes": 2,
        "dt_schema_has_six_groups_as_required": False,
        "actual_board_parent_wiring_verified": False,
        "mainline_ufs_regulator_ready": False,
        "safe_to_attempt_mainline_boot": False, "safe_to_flash": False,
    }

def crosscheck_sources(driver, binding):
    match = re.search(
        r"\nrequired:\s*\n\s*-\s*compatible\s*\n\s*-\s*qcom,pmic-id(?:\s*\n|\Z)",
        binding,
    )
    require(match, "mainline DT binding required fields drifted")
    # Every listed board-parent input is a permitted name for PM8150.
    # Scope matching to the correct PM8150 allOf condition.
    # The same compatible appears in an earlier compatible enum; that
    # occurrence says nothing about the conditional input supply properties.
    condition = re.search(
        r"(?ms)^  - if:\n      properties:\n        compatible:\n"
        r"          enum:\n            - qcom,pm8150-rpmh-regulators\n"
        r".*?(?=^  - if:|\Z)", binding)
    require(condition is not None, "PM8150 conditional schema section absent")
    prop_area = condition.group(0)
    for name in GROUPS:
        if name.startswith("vdd-s"):
            require('"^vdd-s([1-9]|10)-supply$"' in prop_area,
                    "PM8150 SMPS supply naming changed")
        else:
            require(name + ": true" in prop_area,
                    "PM8150 LDO parent property missing: " + name)
    require("vreg->rdesc.supply_name = rpmh_data->supply_name;" in driver and
            "vreg->addr = cmd_db_read_addr(rpmh_resource_name);" in driver,
            "upstream regulator source lookup drifted")
    marker = "static const struct rpmh_vreg_init_data pm8150_vreg_data[] = {"
    require(marker in driver, "PM8150 driver regulator array absent")
    section = driver.split(marker, 1)[1].split("\n};", 1)[0]
    for name, (rails, children) in GROUPS.items():
        for child in children:
            supply = name.removesuffix("-supply")
            expr = (r'RPMH_VREG\("' + child + r'",\s*"[^"]+",\s*&[^,]+,\s*"' +
                    re.escape(supply) + r'"\)')
            require(re.search(expr, section),
                    "mainline supply_name mapping absent: " + child)
    return True

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--binding", type=Path)
    ap.add_argument("--driver", type=Path)
    args = ap.parse_args()
    try:
        g = json.loads(GRAPH.read_text(encoding="utf-8"))
        d = json.loads(P1D.read_text(encoding="utf-8"))
        e = json.loads(P1E.read_text(encoding="utf-8"))
        f = json.loads(P1F.read_text(encoding="utf-8"))
        result = validate(g, d, e, f, P1A_DTS.read_text(encoding="utf-8"),
                          P1C_DTS.read_text(encoding="utf-8"))
        require((args.binding is None) == (args.driver is None),
                "specify both fixed upstream source files")
        if args.binding:
            crosscheck_sources(args.driver.read_text(encoding="utf-8"),
                               args.binding.read_text(encoding="utf-8"))
        result["upstream_crosscheck"] = args.binding is not None
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("P1l offline audit failed: " + str(exc), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
