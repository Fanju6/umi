#!/usr/bin/env python3
"""Read the currently merged umi 4.19 FDT into HOST MEMORY to resolve UFS supplies.

Only report selected UFS phandle links and known PM8150 regulator resources.
Never save or print the raw FDT, serial identifiers or arbitrary node values.
No device writes/mounts/reboots; Root is used solely for a read-only cat.
"""
import argparse
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

MAX_SIZE = 16 * 1024 * 1024
UFS_PROPERTIES = {
    "vdda-phy-supply", "vdda-pll-supply", "vdd-hba-supply",
    "vcc-supply", "vccq-supply", "vccq2-supply",
    "qcom,vddp-ref-clk-supply", "qcom,vccq-parent-supply",
}
TARGET_RESOURCE = {
    "smpa4", "ldoa2", "ldoa5", "ldoa6", "ldoa9",
    "ldoa12", "ldoa17", "smpc8", "bobc1",
}
TARGET_REGULATOR = {
    "pm8150_s4", "pm8150_l2", "pm8150_l5",
    "pm8150_l6", "pm8150_l9", "pm8150_l12",
    "pm8150_l17", "pm8150a_s8", "pm8150a_bob",
}
SAFE_PATH = re.compile(r"^/[A-Za-z0-9,._/@+:-]{0,220}$")

def need(cond, message):
    if not cond:
        raise ValueError(message)

def be_u32(raw):
    return struct.unpack(">I", raw)[0] if len(raw) == 4 else None

def strings(data):
    try:
        return [x.decode("ascii") for x in data.split(b"\0") if x][:8]
    except UnicodeDecodeError:
        return []

def inspect_fdt(data):
    need(40 <= len(data) <= MAX_SIZE, "FDT too small/large")
    magic, total, off_struct, off_strings, off_resv, ver, last, cpu, size_str, size_st = (
        struct.unpack_from(">10I", data, 0))
    need(magic == 0xd00dfeed and 40 <= total <= len(data) <= MAX_SIZE,
         "invalid merged FDT header")
    need(off_struct + size_st <= total and off_strings + size_str <= total
         and off_resv < total and ver >= 16,
         "invalid merged FDT sections")
    end_st = off_struct + size_st
    end_str = off_strings + size_str
    stack = []
    pos = off_struct
    nodes = {}
    refs = []
    model = []
    compatibles = []
    board_id = None
    count = 0
    ended = False
    while pos + 4 <= end_st:
        tag = struct.unpack_from(">I", data, pos)[0]
        pos += 4
        if tag == 1:
            end = data.find(b"\0", pos, end_st)
            need(end >= 0, "bad FDT node name")
            node_name = data[pos:end].decode("ascii", errors="replace")
            need(len(node_name) <= 128 and len(stack) < 128,
                 "oversized FDT node or depth")
            stack.append(node_name)
            pos = (end + 4) & ~3
        elif tag == 2:
            need(stack, "FDT stack underflow")
            stack.pop()
        elif tag == 3:
            need(stack and pos + 8 <= end_st, "truncated FDT property")
            size, name_off = struct.unpack_from(">2I", data, pos)
            pos += 8
            need(pos + size <= end_st and name_off < size_str,
                 "FDT property out of range")
            end = data.find(b"\0", off_strings + name_off, end_str)
            need(end >= 0, "bad FDT property name")
            name = data[off_strings + name_off:end].decode("ascii", errors="replace")
            path = "/" + "/".join(x for x in stack if x)
            value = data[pos:pos + size]
            count += 1
            need(count < 150000, "FDT property limit exceeded")
            if path == "/" and name == "model":
                model = [s for s in strings(value) if len(s) <= 120]
            elif path == "/" and name == "compatible":
                compatibles = [s for s in strings(value) if len(s) <= 120]
            elif path == "/" and name == "qcom,board-id" and size <= 64 and size % 4 == 0:
                board_id = list(struct.unpack(">%dI" % (size // 4), value))
            elif SAFE_PATH.fullmatch(path):
                node = nodes.setdefault(path, {})
                if name in ("phandle", "linux,phandle") and size == 4:
                    node[name] = be_u32(value)
                elif name == "qcom,resource-name":
                    rr = strings(value)
                    if rr and rr[0] in TARGET_RESOURCE:
                        node["resource"] = rr[0]
                elif name == "regulator-name":
                    nn = strings(value)
                    if nn and nn[0] in TARGET_REGULATOR:
                        node["regulator"] = nn[0]
                elif name in UFS_PROPERTIES and re.search(
                        r"(?:1d84000|1d87000|ufshc|ufsphy)", path, re.I):
                    refs.append({"consumer_node": path, "property": name,
                                 "provider_phandle": be_u32(value)})
            pos = (pos + size + 3) & ~3
        elif tag == 4:
            continue
        elif tag == 9:
            need(not stack, "FDT END with unclosed nodes")
            ended = True
            break
        else:
            raise ValueError("unknown FDT structure token")
    need(ended, "merged FDT has no END token")
    providers = {}
    for path, node in nodes.items():
        ph = node.get("phandle", node.get("linux,phandle"))
        if ph is not None and ph != 0:
            providers[ph] = (path, node)
    links = []
    for link in refs:
        ph = link["provider_phandle"]
        candidate = providers.get(ph)
        qualified = bool(candidate and
                         ("resource" in candidate[1] or "regulator" in candidate[1]))
        links.append({
            "consumer_node": link["consumer_node"],
            "property": link["property"],
            "provider_phandle_hex": "0x%08x" % ph if ph is not None else None,
            "provider_resource": candidate[1].get("resource") if qualified else None,
            "provider_regulator": candidate[1].get("regulator") if qualified else None,
            "provider_node": candidate[0] if qualified else None,
            "provider_phandle_found": bool(candidate),
            "known_regulator_resource_resolved": qualified,
        })
    return {
        "device": "umi", "phase": "merged-fdt-ufs-links",
        "runtime_root_model": model, "runtime_root_compatible": compatibles,
        "runtime_root_qcom_board_id": board_id,
        "ufs_supply_links": links,
        "links_observed": len(links),
        "known_regulator_links_resolved": sum(
            bool(l["known_regulator_resource_resolved"]) for l in links),
        "source": "Root read-only /sys/firmware/fdt, filtered HOST-RAM parse",
        "bootloader_selected_dtbo_index_proven": False,
        "mainline_electrical_wiring_proven": False,
        "safe_to_attempt_mainline_boot": False,
        "safe_to_flash": False, "writes_to_device": False,
    }

def collect(adb):
    p = subprocess.run([adb, "shell", "getprop", "ro.product.device"],
                       capture_output=True, timeout=15, check=True)
    need(p.stdout.strip() == b"umi", "connected device is not umi")
    # Binary-safe channel, with read-only cat; never pass a write destination.
    r = subprocess.run([adb, "exec-out", "su", "-c",
                        "cat /sys/firmware/fdt"],
                       capture_output=True, timeout=90, check=True)
    need(len(r.stdout) <= MAX_SIZE, "merged FDT unexpectedly large")
    return inspect_fdt(r.stdout)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--probe", action="store_true",
                   help="explicit Root read-only snapshot of current merged FDT")
    p.add_argument("--adb", default="adb")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if not a.probe:
        p.error("requires explicit --probe")
    try:
        result = collect(a.adb)
        a.output.write_text(json.dumps(result, indent=2, ensure_ascii=False)
                            + "\n", encoding="utf-8")
        print(json.dumps({
            "runtime_root_model": result["runtime_root_model"],
            "runtime_root_qcom_board_id": result["runtime_root_qcom_board_id"],
            "ufs_supply_links": result["links_observed"],
            "known_regulator_links_resolved": result["known_regulator_links_resolved"],
            "safe_to_flash": False,
            "output": str(a.output),
        }, ensure_ascii=False, indent=2))
        return 0
    except ValueError as e:
        print("Merged-FDT metadata validation failed: " + str(e),
              file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as e:
        print("Root read failed (exit %d): merged FDT may be unavailable; "
              "no raw output exposed" % e.returncode, file=sys.stderr)
        return 1
    except (OSError, subprocess.TimeoutExpired):
        print("ADB/Root command unavailable or timed out; no device writes",
              file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
