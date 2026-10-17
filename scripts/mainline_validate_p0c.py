#!/usr/bin/env python3
"""Offline P0c safety regression for 22 fixed and 12 dynamic umi DT nodes.

NOT a boot validation. Never reads raw DT firmware, memory contents or blocks.
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / "config/mainline-umi-p0c-memory.json"
DTS = ROOT / "research/mainline/sm8250-xiaomi-umi-p0c.dts"
OVERRIDE = {
  "xbl_aop_region@80700000": ("xbl_aop_mem", "xbl-aop@80600000"),
  "pil_slpi_region@88c00000": ("slpi_mem", "slpi@88c00000"),
  "pil_adsp_region@8bb00000": ("adsp_mem", "adsp@8bb00000"),
  "pil_spss_region@8e000000": ("spss_mem", "spss@8e000000"),
  "cdsp_secure_heap@8e100000": ("cdsp_secure_heap", "cdsp-secure-heap@8e100000"),
  "res_xbl_uefi_log_region@80880000": ("xbl_uefi_log_mem", "xbl-uefi-log@80880000"),
  "cont_splash_region@9c000000": ("cont_splash_mem", "cont-splash@9c000000"),
  "dfps_data_region@9e300000": ("dfps_data_mem", "dfps-data@9e300000"),
  "disp_rdump_region@9c000000": ("disp_rdump_mem", "disp-rdump@b0400000"),
}
DELETIONS = ("xbl_aop_mem","slpi_mem","adsp_mem","spss_mem","cdsp_secure_heap")

def as_num(value):
    if not isinstance(value,str) or not re.fullmatch(r"0x[0-9a-f]+", value):
        raise ValueError("invalid hex field")
    return int(value,16)

def verify(m, dts):
    if m.get("schema_version")!=1 or m.get("phase")!="P0c" or m.get("device")!="umi":
        raise ValueError("unexpected P0c manifest")
    if (m.get("address_cells"),m.get("size_cells"))!=(2,2):
        raise ValueError("unsupported address/size cells")
    safety=m.get("safety",{})
    if any(safety.get(k) is not False for k in ("safe_to_flash","bootable","android_612_verified","complete_memory_map")):
        raise ValueError("invalid safety gates")
    fixed=m["regions"]["fixed"]; dynamic=m["regions"]["dynamic"]
    if len(fixed)!=22 or len(dynamic)!=12 or len({x["node"] for x in fixed+dynamic})!=34:
        raise ValueError("incomplete/duplicate device memory map")
    ints=[]
    for x in fixed:
        a=as_num(x["base"]); s=as_num(x["size"])
        if s<=0 or a+s>2**64 or x["reusable"]:
            raise ValueError("invalid fixed interval")
        ints.append((a,a+s))
    ints.sort()
    if any(a[1]>b[0] for a,b in zip(ints,ints[1:])):
        raise ValueError("overlapping fixed ranges")
    if sum(b-a for a,b in ints)!=358285312:
        raise ValueError("fixed area total mismatch")
    for x in dynamic:
        if "base" in x or as_num(x["size"])<=0:
            raise ValueError("dynamic region must not have fixed base")
    if sum(as_num(x["size"]) for x in dynamic)!=365035520:
        raise ValueError("dynamic pool total mismatch")
    mailbox=next(x for x in dynamic if x["node"]=="mailbox_region")
    if not mailbox["no_map"] or mailbox["reusable"]:
        raise ValueError("mailbox flags drift")
    if "OFFLINE-ONLY" not in dts or "NOT BOOTABLE" not in dts:
        raise ValueError("DTS lost safety banner")
    body=re.sub(r"/\*.*?\*/|//[^\n]*", "", dts, flags=re.S)
    if 'status = "okay"' in body or 'qcom,board-id' in body or 'qcom,msm-id' in body:
        raise ValueError("research DTS must not enable hardware/board IDs")
    if '#include "sm8250.dtsi"' not in body:
        raise ValueError("unexpected base DTS")
    by_name={x["node"]:x for x in fixed}
    for name,(label,node) in OVERRIDE.items():
        match=re.search(r"\b"+re.escape(label)+r"\s*:\s*"+re.escape(node)+r"\s*\{([^}]+)\}\s*;",body)
        if not match:
            raise ValueError("missing umi DTS node "+node)
        value=by_name[name]; definition=match.group(1)
        reg=f'reg = <0x0 {value["base"]} 0x0 {value["size"]}>;'
        if reg not in definition:
            raise ValueError("incorrect live reg for "+node)
        if ('no-map;' in definition)!=value["no_map"]:
            raise ValueError("no-map differs from live DT for "+node)
    for label in DELETIONS:
        if f"/delete-node/ &{label};" not in body:
            raise ValueError("missing upstream default deletion "+label)
    return {"fixed":22,"dynamic":12,"fixed_mib":341.6875,"dynamic_requested_mib":348.125,
            "live_fixed_overlaps":0,"corrected_or_added_dts_nodes":9,
            "safe_to_flash":False,"bootable":False}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest",type=Path,default=MAPPING)
    ap.add_argument("--dts",type=Path,default=DTS)
    args=ap.parse_args()
    report=verify(json.loads(args.manifest.read_text()),args.dts.read_text())
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
