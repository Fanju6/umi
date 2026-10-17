#!/usr/bin/env python3
"""P1c offline RPMh parent-property topology audit, NOT a voltage configurator."""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "config/mainline-p1c-rpmh-topology.json"
DTS = ROOT / "research/mainline/sm8250-xiaomi-umi-p1c.dts"
P1B = ROOT / "config/mainline-p1b-power.json"
LIVE = ROOT / "config/mainline-p1b-observed.json"
UPSTREAM_SHA = "adc218676eef25575469234709c2d87185ca223a"
VENDOR_SHA = "71b13e62f057a649b77fe4062feb73ee72ad609c"
RAILS = {"pm8150_s4": ("smps4", "vdd-s4-supply"),
         "pm8150_l2": ("ldo2", "vdd-l2-l10-supply"),
         "pm8150_l5": ("ldo5", "vdd-l3-l4-l5-l18-supply"),
         "pm8150_l6": ("ldo6", "vdd-l6-l9-supply"),
         "pm8150_l9": ("ldo9", "vdd-l6-l9-supply"),
         "pm8150_l12": ("ldo12", "vdd-l7-l12-l14-l15-supply"),
         "pm8150_l17": ("ldo17", "vdd-l13-l16-l17-supply")}
FALSE_GATES = ("safe_to_flash", "mainline_board_ready",
               "mainline_kernel_built", "provider_enabled",
               "consumer_nodes_enabled", "boot_image_generated")


def check(data, dts, p1b, live):
    if (data.get("schema_version"), data.get("stage"), data.get("device")) != (1, "P1c", "umi"):
        raise ValueError("expected P1c umi source map")
    src = data.get("sources", {})
    if src.get("upstream", {}).get("sha") != UPSTREAM_SHA or src.get("vendor", {}).get("sha") != VENDOR_SHA:
        raise ValueError("locked source commit mismatch")
    provider = data.get("provider", {})
    if provider.get("compatible") != "qcom,pm8150-rpmh-regulators" or provider.get("dts_parent_label") != "apps_rsc":
        raise ValueError("unexpected RPMh provider model")
    if (provider.get("reference_pmic_id"), provider.get("status")) != ("a", "disabled"):
        raise ValueError("PMIC reference must remain disabled and provisional")
    for key in ("pmic_id_verified_on_umi", "input_supplies_assigned",
                "output_voltages_assigned", "consumer_phandles_connected"):
        if provider.get(key) is not False:
            raise ValueError("P1c forbids claiming validated PMIC inputs or outputs")
    if any(data.get("safety", {}).get(key) is not False for key in FALSE_GATES):
        raise ValueError("P1c may not approve boot, power enable, or flashing")
    if p1b.get("device") != "umi" or p1b.get("phase") != "P1b":
        raise ValueError("P1b source mapping missing")
    supply_consumers = p1b.get("rails", [])
    if len(supply_consumers) != 8 or {x.get("legacy") for x in supply_consumers} != set(RAILS):
        raise ValueError("expected eight UFS/USB references to seven rails")
    observed = {r["name"]: r for r in live.get("rails", [])}
    if set(observed) != set(RAILS):
        raise ValueError("legacy device snapshot is incomplete")
    outputs = data.get("outputs", [])
    if len(outputs) != 7 or {r.get("legacy") for r in outputs} != set(RAILS):
        raise ValueError("P1c provider missing output rails")
    for row in outputs:
        name = row["legacy"]
        child, parent = RAILS[name]
        if row.get("child") != child or row.get("parent_supply_property") != parent:
            raise ValueError("RPMh binding parent group mismatch: " + name)
        if row.get("legacy_observed_microvolts") != observed[name]["observed_microvolts"]:
            raise ValueError("legacy sysfs measurement drift: " + name)
        if row.get("parent_phandle") is not None or row.get("mainline_voltage_range") is not None:
            raise ValueError("unverified power graph/voltage cannot enter P1c manifest")
    if '#include "sm8250-xiaomi-umi-p1a.dts"' not in dts:
        raise ValueError("must reuse P1a disabled controllers and measured carveouts")
    if "RESEARCH-ONLY" not in dts or "NOT BOOTABLE" not in dts:
        raise ValueError("missing explicit research-only safety status")
    body = re.sub(r"/\*.*?\*/|//[^\n]*", "", dts, flags=re.S)
    if not re.search(r'&apps_rsc\s*\{\s*umi_p1c_pm8150\s*:\s*regulators-umi-reference\s*\{', body):
        raise ValueError("provider not located within RPMh RSC")
    if 'compatible = "qcom,pm8150-rpmh-regulators";' not in body or 'qcom,pmic-id = "a";' not in body:
        raise ValueError("unknown or absent RPMh provider metadata")
    if 'status = "disabled";' not in body:
        raise ValueError("RPMh provider must remain disabled")
    forbidden = ("regulator-min-microvolt", "regulator-max-microvolt",
                 "regulator-always-on", "regulator-boot-on", "regulator-initial-mode",
                 "regulator-name", "vdd-", "vcc-supply", "vccq-supply",
                 "vdda-phy-supply", "vdda-pll-supply", 'status = "okay"')
    for needle in forbidden:
        if needle in body:
            raise ValueError("unexpected live voltage/wiring/power configuration: " + needle)
    for row in outputs:
        child = row["child"]
        label = "umi_p1c_" + row["legacy"].split("_")[-1]
        if not re.search(r"\b" + re.escape(label) + r"\s*:\s*" +
                         re.escape(child) + r"\s*\{\s*\};", body):
            raise ValueError("unreviewed regulator child or missing label: " + child)
    return {
        "stage": "P1c", "provider_status": "disabled",
        "PM8150_outputs_modeled": len(outputs),
        "distinct_parent_property_groups": len({x["parent_supply_property"] for x in outputs}),
        "legacy_supply_edges_accounted": len(supply_consumers),
        "parent_phandles_verified": False, "voltages_applied": False,
        "mainline_bootable": False, "safe_to_flash": False,
    }


def check_sources(binding, soc, elish):
    if "apps_rsc: rsc@18200000" not in soc:
        raise ValueError("upstream apps_rsc label changed")
    start = binding.find("allOf:")
    if start < 0:
        raise ValueError("upstream binding missing allOf")
    pos = binding.find("            - qcom,pm8150-rpmh-regulators", start)
    if pos < 0:
        raise ValueError("PM8150 supply group missing in binding")
    end = binding.find("\n  - if:", pos)
    scope = binding[pos:end if end > pos else None]
    for entry in RAILS.values():
        parent = entry[1]
        # PM8150 smps supplies are authorized by YAML patternProperties,
        # not enumerated as literal "vdd-s4-supply: true" keys.
        listed = parent + ": true" in scope
        s4_pattern = (parent == "vdd-s4-supply" and
                      '"^vdd-s([1-9]|10)-supply$": true' in scope)
        if not (listed or s4_pattern):
            raise ValueError("PM8150 regulator parent supply name not in source: " + parent)
    if 'compatible = "qcom,pm8150-rpmh-regulators";' not in elish or 'qcom,pmic-id = "a";' not in elish:
        raise ValueError("PMIC-ID example not found in locked reference board")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--matrix", type=Path, default=MATRIX)
    ap.add_argument("--dts", type=Path, default=DTS)
    ap.add_argument("--p1b", type=Path, default=P1B)
    ap.add_argument("--observed", type=Path, default=LIVE)
    ap.add_argument("--binding", type=Path)
    ap.add_argument("--soc", type=Path)
    ap.add_argument("--reference-board", type=Path)
    args = ap.parse_args()
    try:
        m = json.loads(args.matrix.read_text(encoding="utf-8"))
        p1b = json.loads(args.p1b.read_text(encoding="utf-8"))
        live = json.loads(args.observed.read_text(encoding="utf-8"))
        result = check(m, args.dts.read_text(encoding="utf-8"), p1b, live)
        sources = (args.binding, args.soc, args.reference_board)
        if any(src is None for src in sources) and not all(src is None for src in sources):
            raise ValueError("source checking requires all three locked files")
        if all(src is not None for src in sources):
            check_sources(*(src.read_text(encoding="utf-8") for src in sources))
            result["locked_source_evidence_checked"] = True
        else:
            result["locked_source_evidence_checked"] = False
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
        print(f"P1c topology validation failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
