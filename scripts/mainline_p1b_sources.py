#!/usr/bin/env python3
"""Offline P1b source crosscheck. Source files must come from pinned commits."""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "config/mainline-p1b-power.json"
UPSTREAM_SHA = "adc218676eef25575469234709c2d87185ca223a"
VENDOR_SHA = "71b13e62f057a649b77fe4062feb73ee72ad609c"
CONSUMERS = {"ufs_mem_hc", "ufs_mem_phy", "usb_1_hsphy"}


def inspect_matrix(m):
    if m.get("schema_version") != 1 or (m.get("phase"), m.get("device")) != ("P1b", "umi"):
        raise ValueError("不是 P1b umi 的证据矩阵")
    if m.get("upstream", {}).get("sha") != UPSTREAM_SHA or m.get("vendor", {}).get("sha") != VENDOR_SHA:
        raise ValueError("源码 Git SHA 未锁定")
    if any(m.get("safety", {}).get(k) is not False for k in
           ("safe_to_flash", "ufs_enabled", "usb_enabled", "regulators_verified", "boot_image_available")):
        raise ValueError("研究阶段安全门禁不能绕过")
    rails = m.get("rails", [])
    if len(rails) != 8 or {r.get("consumer") for r in rails} != CONSUMERS:
        raise ValueError("UFS / USB 供电映射缺失")
    for rail in rails:
        if rail.get("live_voltage_verified") is not False:
            raise ValueError("无实机数据不得标记电压验证通过")
        if rail.get("mainline_candidate", "").startswith("vreg_"):
            raise ValueError("不能把其他设备 DTS 标签直接作为 umi 结论")
    if m.get("typec", {}).get("upstream_default_disabled") is not True:
        raise ValueError("PM8150B Type-C 必须记录为上游默认 disabled")
    if m.get("typec", {}).get("role_graph_verified") is not False:
        raise ValueError("Type-C 角色未通过实机验证")


def _node(src, label):
    pat = r"\b" + re.escape(label) + r"\s*:\s*[-\w@,]+\s*\{"
    match = re.search(pat, src)
    if not match:
        raise ValueError("源文件未出现标签：" + label)
    # Enough for the PM8150B VBUS and Type-C status which is near node start.
    return src[match.end():match.end() + 350]


def inspect_sources(m, upstream_soc, upstream_pmicb, vendor_common, vendor_usb, vendor_umi):
    inspect_matrix(m)
    for label in ("ufs_mem_hc", "ufs_mem_phy", "usb_1_hsphy"):
        _node(upstream_soc, label)
    for label in ("pm8150b_typec", "pm8150b_vbus"):
        if 'status = "disabled";' not in _node(upstream_pmicb, label):
            raise ValueError(label + " 不是主线默认 disabled")
    for entry in m["rails"]:
        vendor = vendor_usb if entry["consumer"] == "usb_1_hsphy" else vendor_common
        phrase = entry["property"] + " = <&" + entry["legacy"] + ">;"
        if phrase not in vendor:
            raise ValueError("4.19 供电线索不符：" + phrase)
    for phrase in ('maximum-speed = "high-speed";', "status = \"disabled\";"):
        if phrase not in vendor_common:
            raise ValueError("umi 共用 USB 限制证据缺失")
    if "pm8150b_pdphy" not in vendor_umi or "ext_5v_boost" not in vendor_umi:
        raise ValueError("umi 厂商 USB PD / VBUS 线索缺失")
    return {"phase": "P1b", "matched_rails": 8,
            "pm8150b_typec_default_disabled": True,
            "pm8150b_vbus_default_disabled": True,
            "safe_to_flash": False, "actual_umi_voltage_verified": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--matrix", type=Path, default=MATRIX)
    p.add_argument("--upstream-soc", type=Path)
    p.add_argument("--upstream-pmicb", type=Path)
    p.add_argument("--vendor-common", type=Path)
    p.add_argument("--vendor-usb", type=Path)
    p.add_argument("--vendor-umi", type=Path)
    a = p.parse_args()
    m = json.loads(a.matrix.read_text(encoding="utf-8"))
    inspect_matrix(m)
    files = [a.upstream_soc, a.upstream_pmicb, a.vendor_common, a.vendor_usb, a.vendor_umi]
    if any(x is None for x in files) and not all(x is None for x in files):
        raise ValueError("源码检查必须完整传入 5 个固定文件")
    report = {"phase": "P1b", "matrix_checked": True, "source_checked": False,
              "safe_to_flash": False}
    if all(x is not None for x in files):
        texts = [x.read_text(encoding="utf-8") for x in files]
        report.update(inspect_sources(m, *texts))
        report["source_checked"] = True
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
