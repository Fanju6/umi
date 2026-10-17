#!/usr/bin/env python3
"""P1d: verify pinned umi Kona VRM resources, PM8150 ID inference and UFS extras.
Offline only: cannot change hardware, never authorizes mainline supplies/boot.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "config/mainline-p1d-rpmh-evidence.json"
P1C = ROOT / "config/mainline-p1c-rpmh-topology.json"
PIN_VENDOR = "71b13e62f057a649b77fe4062feb73ee72ad609c"
PIN_UPSTREAM = "adc218676eef25575469234709c2d87185ca223a"
RESOURCES = {
    "pm8150_s4": "smpa4", "pm8150_l2": "ldoa2",
    "pm8150_l5": "ldoa5", "pm8150_l6": "ldoa6",
    "pm8150_l9": "ldoa9", "pm8150_l12": "ldoa12",
    "pm8150_l17": "ldoa17",
}
PARENTS = {
    "pm8150_s4": "vdd-s4-supply",
    "pm8150_l2": "vdd-l2-l10-supply",
    "pm8150_l5": "vdd-l3-l4-l5-l18-supply",
    "pm8150_l6": "vdd-l6-l9-supply",
    "pm8150_l9": "vdd-l6-l9-supply",
    "pm8150_l12": "vdd-l7-l12-l14-l15-supply",
    "pm8150_l17": "vdd-l13-l16-l17-supply",
}
EXTRAS = {
    "qcom,vddp-ref-clk-supply": "pm8150_l6",
    "qcom,vccq-parent-supply": "pm8150a_s8",
}
FALSE_GATES = (
    "board_parent_wiring_verified", "regulator_voltage_safety_verified",
    "pmic_id_tested_on_mainline", "safe_to_flash", "boot_image_created"
)


def validate(graph, p1c):
    if (graph.get("schema_version"), graph.get("stage"), graph.get("device")) != (1, "P1d", "umi"):
        raise ValueError("invalid P1d identity")
    if graph.get("locked") != {"upstream": PIN_UPSTREAM, "vendor": PIN_VENDOR}:
        raise ValueError("source SHA mismatch")
    identity = graph.get("provider_identity", {})
    if identity.get("legacy_resource_suffix") != "a" or identity.get("mainline_candidate_pmic_id") != "a":
        raise ValueError("unexpected PMIC ID source hypothesis")
    if identity.get("safe_to_enable") is not False:
        raise ValueError("PMIC ID inference is not a boot authorization")
    flags = graph.get("boundaries", {})
    if any(flags.get(k) is not False for k in FALSE_GATES) or flags.get("no_enabled_hardware") is not True:
        raise ValueError("P1d must remain offline-only and nonflashable")
    needed = {"legacy_mainline_ufs_supply_edges": 5, "legacy_ufs_extra_vendor_edges": 2,
              "legacy_usb2_phy_supply_edges": 3, "parent_input_properties": 6,
              "distinct_physical_rails": 7}
    if any(flags.get(k) != v for k, v in needed.items()):
        raise ValueError("P1d edge counts changed")
    rails = graph.get("rails", [])
    if len(rails) != 7 or {r.get("legacy") for r in rails} != set(RESOURCES):
        raise ValueError("P1d seven-rail evidence incomplete")
    old = {r["legacy"]: r for r in p1c.get("outputs", [])}
    if set(old) != set(RESOURCES):
        raise ValueError("P1c baseline missing")
    for r in rails:
        name = r["legacy"]
        prior = old[name]
        if (r.get("resource"), r.get("mainline_child"), r.get("parent_property")) != (
                RESOURCES[name], prior["child"], PARENTS[name]):
            raise ValueError("mismatched VRM resource or binding property: " + name)
        if r.get("live_uv") != prior["legacy_observed_microvolts"]:
            raise ValueError("observed legacy voltage evidence drift")
        if any(r.get(k) is not None for k in ("parent_supply_phandle", "mainline_constraint_uv")):
            raise ValueError("unknown supply/voltage must remain null")
        if r.get("resource_id_suffix") != "a" or r.get("mainline_pm_id_boot_verified") is not False:
            raise ValueError("incorrect mainline PMIC ID confidence")
    extras = graph.get("extra_ufs_dependencies", [])
    if len(extras) != 2 or {x.get("property"): x.get("vendor_phandle") for x in extras} != EXTRAS:
        raise ValueError("legacy UFS extra supply votes missing")
    if any(x.get("mainline_binding_verified") is not False for x in extras):
        raise ValueError("vendor-only UFS properties not validated on mainline")
    return {"phase": "P1d", "locked_resources": 7, "rpmh_suffix": "a",
            "mainline_pmic_id_proven": False, "missing_parent_phandles": 7,
            "extra_ufs_vendor_edges": 2, "safe_to_flash": False}


def verify_sources(graph, kona, vrm, common, umi, binding, elish):
    if '#include "kona-regulators.dtsi"' not in kona:
        raise ValueError("Kona base omits regulator source")
    if '#include "xiaomi-sm8250-common.dtsi"' not in umi:
        raise ValueError("umi vendor include chain missing")
    for name, resource in RESOURCES.items():
        # Check the exact VRM block (the first child is the canonical physical rail).
        pattern = (r"rpmh-regulator-" + re.escape(resource) +
                   r"\s*\{\s*compatible\s*=\s*\"qcom,rpmh-vrm-regulator\";" +
                   r"(?:(?!rpmh-regulator-).)*?"
                   + re.escape(name) + r"\s*:\s*regulator-pm8150-")
        if not re.search(pattern, vrm, re.S):
            raise ValueError("legacy RPMh VRM evidence changed: " + name)
    for prop, target in EXTRAS.items():
        exact = prop + " = <&" + target + ">;"
        if exact not in common:
            raise ValueError("legacy extra UFS dependency missing: " + exact)
    # The binding names determine a property group, not which actual voltage source
    # is physically wired on this specific board.
    pos = binding.find("            - qcom,pm8150-rpmh-regulators")
    end = binding.find("\n  - if:", pos)
    if pos < 0 or end < 0:
        raise ValueError("mainline RPMh binding layout changed")
    relevant = binding[pos:end]
    for parent in set(PARENTS.values()):
        if parent + ": true" not in relevant and not (
                parent == "vdd-s4-supply" and "^vdd-s([1-9]|10)-supply$" in relevant):
            raise ValueError("mainline PM8150 input property missing: " + parent)
    if 'qcom,pmic-id = "a";' not in elish:
        raise ValueError("reference PMIC ID example missing")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", type=Path, default=GRAPH)
    ap.add_argument("--p1c", type=Path, default=P1C)
    for arg in ("kona", "vrm", "common", "umi", "binding", "elish"):
        ap.add_argument("--" + arg, type=Path)
    args = ap.parse_args()
    try:
        graph = json.loads(args.graph.read_text(encoding="utf-8"))
        p1c = json.loads(args.p1c.read_text(encoding="utf-8"))
        result = validate(graph, p1c)
        sources = (args.kona, args.vrm, args.common, args.umi, args.binding, args.elish)
        if any(x is None for x in sources) and not all(x is None for x in sources):
            raise ValueError("need all six pinned sources for source verification")
        if all(x is not None for x in sources):
            verify_sources(graph, *(p.read_text(encoding="utf-8") for p in sources))
            result["source_crosscheck"] = True
        else:
            result["source_crosscheck"] = False
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"P1d audit failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
