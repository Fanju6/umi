#!/usr/bin/env python3
"""P1f: audited UFS vendor regulator votes, pinned-source only. No hardware access."""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "config/mainline-p1f-ufs-lifecycle.json"
P1E = ROOT / "config/mainline-p1e-ufs-parent-graph.json"
OLD = "71b13e62f057a649b77fe4062feb73ee72ad609c"
NEW = "adc218676eef25575469234709c2d87185ca223a"
VOTES = {
    "vddp": ("qcom,vddp-ref-clk-supply", "pm8150_l6", 100,
             "enable", "disable", "set_min_load", "enable_or_restore_load"),
    "vccq_parent": ("qcom,vccq-parent-supply", "pm8150a_s8", 210000,
                    "set_load", "conditional_unvote", "conditional_unvote", "restore_load"),
}
SHARED = {
    "vdd-wlan-rfa2-supply": ("kona.dtsi", "pm8150a_s8"),
    "qca,bt-vdd-rfa2-supply": ("xiaomi-sm8250-common.dtsi", "pm8150a_s8"),
}
SOURCE_NAMES = ("legacy_ufs", "legacy_common", "legacy_kona", "new_ufs",
                "new_platform", "new_ufs_binding", "new_common_binding")

def require(cond, message):
    if not cond:
        raise ValueError(message)

def c_function(src, name):
    m = re.search(r"\b(?:static\s+)?(?:int|void)\s+" + re.escape(name) +
                  r"\s*\(", src)
    require(m, "missing function " + name)
    end = src.find("\n}", m.end())
    require(end > m.end(), "incomplete function " + name)
    return src[m.start():end + 2]

def validate(g, p1e):
    require((g.get("schema_version"), g.get("stage"), g.get("device")) ==
            (1, "P1f", "umi"), "P1f identity")
    require(g.get("locked") == p1e.get("locked") ==
            {"vendor": OLD, "upstream": NEW}, "pinned source drift")
    flags = g.get("boundaries", {})
    require(set(flags) == {"safe_to_flash", "boot_image_created",
                           "hardware_nodes_enabled", "recovery_and_logging_verified"}
            and all(v is False for v in flags.values()), "unsafe research gates")
    require(all(v is False for v in p1e.get("safety", {}).values()), "P1e safety drift")
    votes = g.get("votes", [])
    require(len(votes) == 2 and {v.get("name") for v in votes} == set(VOTES),
            "P1f vote identities")
    for v in votes:
        got = tuple(v.get(k) for k in (
            "property", "source", "max_uA_in_vendor_dts", "init",
            "link_off", "hibern8", "resume"))
        require(got == VOTES[v["name"]], "vote lifecycle drift " + v["name"])
        require(v.get("mainline_replacement") is None, "unsupported vote replacement")
    expected = {v["property"]: v["vendor_target"] for v in p1e["legacy_ufs_votes"]}
    require({v["property"]: v["source"] for v in votes} == expected,
            "P1e extra UFS graph changed")
    shared = g.get("shared_s8c_references", [])
    require(len(shared) == 2 and
            {r.get("property"): (r.get("source_file"), r.get("ref"))
             for r in shared} == SHARED, "shared S8C consumer edge drift")
    facts = g.get("interpretation", {})
    require(set(facts) == {"vccq_parent_direct_enable", "mainline_equivalent_proven",
                          "board_wiring_proven", "vendor_current_properties_are_measurements",
                          "mainline_pmic_probed", "fixed_vph_voltage_uv"} and
            all(v is False for k, v in facts.items() if k != "fixed_vph_voltage_uv")
            and facts["fixed_vph_voltage_uv"] is None,
            "unverified power conclusion")
    require(len(p1e["parent_inputs"]) == 6 and
            all(x["umi_parent_phandle"] is None for x in p1e["parent_inputs"]),
            "unverified parent supply inserted")
    return {"stage": "P1f", "vendor_vote_paths": 2, "shared_s8c_references": 2,
            "unknown_parent_groups": 6, "mainline_vote_migration_verified": False,
            "safe_to_flash": False}

def verify_sources(g, s):
    require(set(s) == set(SOURCE_NAMES), "incomplete pinned source set")
    common, kona, legacy = s["legacy_common"], s["legacy_kona"], s["legacy_ufs"]
    for v in g["votes"]:
        prop = v["property"]
        require(re.search(re.escape(prop) + r"\s*=\s*<&" +
                          v["source"] + r">;", common), "vendor UFS phandle missing: " + prop)
        microamps = prop.removesuffix("-supply") + "-max-microamp"
        require(re.search(re.escape(microamps) + r"\s*=\s*<" +
                          str(v["max_uA_in_vendor_dts"]) + r">;", common),
                "vendor UFS max-load property missing: " + microamps)
    for prop, (filename, target) in SHARED.items():
        source = kona if filename == "kona.dtsi" else common
        require(re.search(re.escape(prop) + r"\s*=\s*<&" + target + r">;", source),
                "S8C shared reference missing: " + prop)

    init = c_function(legacy, "ufs_qcom_init")
    suspend = c_function(legacy, "ufs_qcom_suspend")
    resume = c_function(legacy, "ufs_qcom_resume")
    parser = c_function(legacy, "ufs_qcom_parse_reg_info")
    configure = c_function(legacy, "ufs_qcom_config_vreg")
    enable = c_function(legacy, "ufs_qcom_enable_vreg")
    disable = c_function(legacy, "ufs_qcom_disable_vreg")
    for prop, member in (("qcom,vddp-ref-clk", "vddp_ref_clk"),
                         ("qcom,vccq-parent", "vccq_parent")):
        require(re.search(r'ufs_qcom_parse_reg_info\s*\(\s*host,\s*"' +
                          re.escape(prop) + '"', init), "legacy regulator acquisition missing")
        require("host->" + member in suspend and "host->" + member in resume,
                "legacy suspend/resume regulator path missing")
    require('"%s-supply", name' in parser and
            '"%s-max-microamp", name' in parser and
            "devm_regulator_get(dev, vreg->name)" in parser,
            "legacy phandle / load parser changed")
    require("regulator_set_load" in configure and
            "regulator_set_voltage" in configure and
            "if (vreg->min_uV && vreg->max_uV)" in configure,
            "legacy regulator load vs voltage behavior changed")
    require("regulator_enable(vreg->reg)" in enable and
            "regulator_disable(vreg->reg)" in disable,
            "legacy regulator enable/disable behavior changed")
    require(re.search(r"ufs_qcom_enable_vreg\s*\(\s*dev,\s*host->vddp_ref_clk", init),
            "legacy VDDP initial enable missing")
    require(re.search(r"ufs_qcom_config_vreg\s*\(\s*hba->dev,\s*host->vccq_parent,\s*true", init),
            "legacy VCCQ parent initial load vote missing")
    require("ufs_qcom_disable_vreg(hba->dev," in suspend and
            "ufshcd_qcom_set_vreg_load(host->vddp_ref_clk" in suspend,
            "legacy VDDP off vs Hibern8 vote changed")
    require("!hba->auto_bkops_enabled" in suspend and
            "host->vccq_parent, false" in suspend,
            "legacy VCCQ suspend conditional vote changed")
    require("host->vddp_ref_clk->max_uA" in resume and
            "host->vccq_parent, true" in resume,
            "legacy resume vote behavior changed")
    require('ufshcd_populate_vreg(dev, "vccq"' in s["new_platform"] and
            'ufshcd_populate_vreg(dev, "vccq2"' in s["new_platform"],
            "mainline standard vccq parsing absent")
    require("ufs_qcom_dev_ref_clk_ctrl" in s["new_ufs"],
            "mainline ref clock handler absent")
    for prop in ("qcom,vddp-ref-clk", "qcom,vccq-parent"):
        for key in ("new_ufs", "new_platform", "new_ufs_binding", "new_common_binding"):
            require(prop not in s[key], "vendor property appeared in mainline: " + key)
    return True

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", type=Path, default=GRAPH)
    ap.add_argument("--p1e", type=Path, default=P1E)
    for name in SOURCE_NAMES:
        ap.add_argument("--" + name.replace("_", "-"), type=Path)
    args = ap.parse_args()
    try:
        g = json.loads(args.graph.read_text(encoding="utf-8"))
        p1e = json.loads(args.p1e.read_text(encoding="utf-8"))
        result = validate(g, p1e)
        paths = {k: getattr(args, k) for k in SOURCE_NAMES}
        selected = {k for k, p in paths.items() if p is not None}
        require(not selected or selected == set(SOURCE_NAMES),
                "supply all seven pinned files or none")
        if selected:
            verify_sources(g, {k: p.read_text(encoding="utf-8")
                               for k, p in paths.items()})
        result["source_crosscheck"] = bool(selected)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("P1f audit failed: " + str(exc), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
