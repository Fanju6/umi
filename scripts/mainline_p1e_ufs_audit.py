#!/usr/bin/env python3
"""P1e audit of umi 4.19 versus mainline 6.12 UFS and RPMh dependencies.

Offline only: no ADB, no hardware operations, no voltage programming.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "config/mainline-p1e-ufs-parent-graph.json"
P1D = ROOT / "config/mainline-p1d-rpmh-evidence.json"
P1A = ROOT / "research/mainline/sm8250-xiaomi-umi-p1a.dts"
P1C = ROOT / "research/mainline/sm8250-xiaomi-umi-p1c.dts"
VENDOR = "71b13e62f057a649b77fe4062feb73ee72ad609c"
UPSTREAM = "adc218676eef25575469234709c2d87185ca223a"
PARENTS = {
    "vdd-s4-supply", "vdd-l2-l10-supply", "vdd-l3-l4-l5-l18-supply",
    "vdd-l6-l9-supply", "vdd-l7-l12-l14-l15-supply", "vdd-l13-l16-l17-supply",
}
EXTRAS = {
    "qcom,vddp-ref-clk-supply": "pm8150_l6",
    "qcom,vccq-parent-supply": "pm8150a_s8",
}
RESOURCES = {
    "pm8150a_s8": ("smpc8", "smps8", "smp%s8"),
    "pm8150a_bob": ("bobc1", "bob", "bob%s1"),
}
CLOCKS = [
    "core_clk", "bus_aggr_clk", "iface_clk", "core_clk_unipro",
    "ref_clk", "tx_lane0_sync_clk", "rx_lane0_sync_clk", "rx_lane1_sync_clk",
]
FILES = ("vendor_vrm", "vendor_common", "vendor_umi", "soc", "reg_driver",
         "rpmh_binding", "ufs_binding", "ufs_common", "phy_binding",
         "ufs_driver", "ufs_platform")

def need(test, error):
    if not test:
        raise ValueError(error)

def verify_dts_safety(p1a, p1c):
    for label in ("ufs_mem_hc", "ufs_mem_phy", "usb_1", "usb_1_dwc3",
                  "usb_1_hsphy", "usb_1_qmpphy"):
        expr = r"&" + label + r"\s*\{\s*status\s*=\s*\"disabled\";\s*\};"
        need(re.search(expr, p1a), "not disabled: " + label)
    need(re.search(r"regulators-umi-reference\s*\{[^{}]*status\s*=\s*\"disabled\";", p1c, re.S),
         "P1c provider not disabled")
    for bad in ("regulator-min-microvolt", "regulator-max-microvolt",
                "regulator-always-on", "regulator-boot-on", "vdd-s4-supply"):
        need(bad not in p1c, "unsafe P1c provider mutation: " + bad)

def validate(g, p1d, p1a=None, p1c=None):
    need((g.get("schema_version"), g.get("stage"), g.get("device")) == (1, "P1e", "umi"),
         "P1e identity")
    need(g.get("locked") == p1d.get("locked") ==
         {"vendor": VENDOR, "upstream": UPSTREAM}, "pinned source mismatch")
    flags = g.get("safety", {})
    expected = {"safe_to_flash", "boot_image_created", "provider_enabled", "ufs_enabled",
                "usb_enabled", "pmic_probe_verified", "board_parent_wiring_verified",
                "voltage_safety_verified", "ufs_vote_migration_verified",
                "recovery_and_logging_verified"}
    need(set(flags) == expected and all(v is False for v in flags.values()),
         "unsafe P1e safety gates")
    need(p1d.get("boundaries", {}).get("safe_to_flash") is False, "P1d safety changed")
    resources = g.get("pm8150a_resources", [])
    need(len(resources) == 2 and {x.get("vendor_label") for x in resources} == set(RESOURCES),
         "missing PM8150A S8/BOB")
    for r in resources:
        need((r.get("vrm_resource"), r.get("child"), r.get("driver_template")) ==
             RESOURCES[r["vendor_label"]], "incorrect RPMh resource mapping")
        need(r.get("pmic_suffix") == "c" and r.get("boot_verified") is False and
             r.get("mainline_candidate") == "qcom,pm8150l-rpmh-regulators",
             "unverified PMIC ID promoted to hardware proof")
    inputs = g.get("parent_inputs", [])
    need(len(inputs) == 6 and {r.get("property") for r in inputs} == PARENTS,
         "missing input property groups")
    need(all(r.get("umi_parent_phandle") is None for r in inputs),
         "unknown board parent phandle is not null")
    extras = g.get("legacy_ufs_votes", [])
    need(len(extras) == 2 and
         {r.get("property"): r.get("vendor_target") for r in extras} == EXTRAS,
         "missing legacy vendor UFS vote")
    need(all(r.get("mainline_equivalent") is None for r in extras),
         "unmapped vendor UFS vote was declared migrated")
    need({r.get("property"): r.get("vendor_phandle")
          for r in p1d.get("extra_ufs_dependencies", [])} == EXTRAS, "P1d vote regression")
    h = g.get("mainline_ufs", {})
    need((h.get("controller"), h.get("phy"), h.get("status")) ==
         ("ufs_mem_hc", "ufs_mem_phy", "disabled"), "UFS node identity/status changed")
    need(h.get("clocks") == CLOCKS and h.get("phy_clocks") == ["ref", "ref_aux", "qref"],
         "UFS clock dependency drift")
    need((h.get("controller_reset"), h.get("phy_reset"), h.get("power_domain")) ==
         ("GCC_UFS_PHY_BCR", "ufs_mem_hc 0", "UFS_PHY_GDSC"), "UFS reset/PD drift")
    need(h.get("iommu_streams") == ["0x0e0", "0x4e0"] and
         h.get("interconnects") == ["ufs-ddr", "cpu-ufs"], "UFS IOMMU/ICC drift")
    need(h.get("ufs_supplies") == ["vcc-supply", "vccq-supply", "vccq2-supply"] and
         h.get("phy_supplies") == ["vdda-phy-supply", "vdda-pll-supply"] and
         h.get("regulator_phandles_verified") is False, "missing/incorrect supply graph")
    vph = g.get("vph_pwr", {})
    need(vph.get("fixed_regulator_input_verified") is False and
         vph.get("mainline_voltage_uv") is None, "ADC VPH_PWR misused as fixed voltage")
    if p1a is not None or p1c is not None:
        need(p1a is not None and p1c is not None, "partial DTS evidence")
        verify_dts_safety(p1a, p1c)
    return {"stage": "P1e", "verified_candidate_suffix": "c", "unknown_parent_groups": 6,
            "unmapped_legacy_votes": 2, "safe_to_flash": False}

def source_block(s, marker, close):
    start = s.find(marker)
    need(start >= 0, "pinned source marker missing: " + marker)
    end = s.find(close, start + len(marker))
    need(end > start, "unterminated pinned source block: " + marker)
    return s[start:end]

def verify_sources(g, sources):
    need(set(sources) == set(FILES), "incomplete pinned sources")
    for r in g["pm8150a_resources"]:
        block = source_block(sources["vendor_vrm"],
                             "rpmh-regulator-" + r["vrm_resource"] + " {", "\n\t};")
        need('qcom,resource-name = "' + r["vrm_resource"] + '";' in block and
             re.search(r"\b" + r["vendor_label"] + r"\s*:", block),
             "4.19 VRM resource mismatch: " + r["vendor_label"])
    common = sources["vendor_common"]
    for prop, ref in EXTRAS.items():
        need(re.search(re.escape(prop) + r"\s*=\s*<&" + ref + r">;", common),
             "4.19 extra UFS vote missing: " + prop)
    need("vph_pwr@83" in sources["vendor_umi"] and
         'label = "vph_pwr";' in sources["vendor_umi"], "VPH_PWR ADC evidence missing")
    regulator = source_block(sources["reg_driver"],
               "static const struct rpmh_vreg_init_data pm8150l_vreg_data[]", "\n};")
    for r in g["pm8150a_resources"]:
        pattern = r'RPMH_VREG\("' + r["child"] + r'",\s*"' + re.escape(r["driver_template"]) + '"'
        need(re.search(pattern, regulator), "6.12 PM8150L driver resource drift")
    rb = sources["rpmh_binding"]
    need("qcom,pm8150l-rpmh-regulators" in rb and
         "vdd-bob-supply:" in rb and '"^vdd-s[1-8]-supply$"' in rb,
         "PM8150L regulator binding drift")
    for name in PARENTS:
        need(name + ":" in rb or (name == "vdd-s4-supply" and
             "^vdd-s([1-9]|10)-supply$" in rb), "PM8150 parent binding missing: " + name)
    soc = sources["soc"]
    host = source_block(soc, "ufs_mem_hc: ufshc@1d84000 {", "\n\t\t};")
    phy = source_block(soc, "ufs_mem_phy: phy@1d87000 {", "\n\t\t};")
    for name in CLOCKS:
        need('"' + name + '"' in host, "host clock missing: " + name)
    for term in ("GCC_UFS_PHY_BCR", "UFS_PHY_GDSC", "0x0e0", "0x4e0",
                 '"ufs-ddr"', '"cpu-ufs"', '"disabled"'):
        need(term in host, "host dependency missing: " + term)
    for term in ('"ref"', '"ref_aux"', '"qref"', "resets = <&ufs_mem_hc 0>",
                 "UFS_PHY_GDSC", '"disabled"'):
        need(term in phy, "PHY dependency missing: " + term)
    for name in ("vdda-phy-supply", "vdda-pll-supply"):
        need(name not in phy and name in sources["phy_binding"],
             "PHY binding/board supply audit changed: " + name)
    need("qcom,sm8250-ufshc" in sources["ufs_binding"] and
         "qcom,sm8250-qmp-ufs-phy" in sources["phy_binding"], "UFS schema compatible drift")
    for name in ("vcc-supply", "vccq-supply", "vccq2-supply"):
        need(name + ":" in sources["ufs_common"], "standard UFS supply missing: " + name)
    need('ufshcd_populate_vreg(dev, "vccq"' in sources["ufs_platform"] and
         "ufs_qcom_dev_ref_clk_ctrl" in sources["ufs_driver"],
         "mainline regulator/ref-clock behavior changed")
    for name in EXTRAS:
        for key in ("ufs_binding", "ufs_common", "ufs_driver", "ufs_platform"):
            need(name not in sources[key], "vendor-only UFS property now upstream: re-audit")
    return True

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", type=Path, default=GRAPH)
    ap.add_argument("--p1d", type=Path, default=P1D)
    for key in FILES:
        ap.add_argument("--" + key.replace("_", "-"), type=Path)
    args = ap.parse_args()
    try:
        g = json.loads(args.graph.read_text(encoding="utf-8"))
        p1d = json.loads(args.p1d.read_text(encoding="utf-8"))
        result = validate(g, p1d, P1A.read_text(encoding="utf-8"), P1C.read_text(encoding="utf-8"))
        paths = {key: getattr(args, key) for key in FILES}
        chosen = {key for key, val in paths.items() if val is not None}
        need(not chosen or chosen == set(FILES), "all 11 pinned paths required together")
        if chosen:
            verify_sources(g, {key: val.read_text(encoding="utf-8")
                               for key, val in paths.items()})
        result["source_crosscheck"] = bool(chosen)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("P1e audit failed: " + str(exc), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
