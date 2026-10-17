#!/usr/bin/env python3
"""Compare selected live umi DT reg metadata with pinned Linux 6.12 SM8250 defaults.

Fully offline and read-only. No ADB, Root, partition access or firmware operations.
Input is the user-reviewed output of mainline_reserved_memory_probe.py.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "config/mainline-612-reserved-memory.json"


def number(value):
    if not isinstance(value, str) or not value.startswith("0x"):
        raise ValueError("内存地址和尺寸必须采用十六进制字符串")
    n = int(value, 16)
    if n < 0 or n >= 1 << 64:
        raise ValueError("内存值不在 uint64 范围内")
    return n


def validate(source, report):
    if source.get("schema_version") != 1 or source.get("source", {}).get("commit") != "adc218676eef25575469234709c2d87185ca223a":
        raise ValueError("未审核的 Linux 6.12 上游内存基线")
    if source.get("safety", {}).get("safe_to_flash") is not False:
        raise ValueError("基线不允许表示可刷机")
    if report.get("device") != "umi" or report.get("phase") != "P0b-reg":
        raise ValueError("只接受 umi P0b-reg 格式的设备树报告")
    if (report.get("address_cells"), report.get("size_cells")) != (2, 2):
        raise ValueError("期望 DT 64-bit address/size-cells")
    if report.get("safe_to_flash") is not False or report.get("memory_contents_read") is not False:
        raise ValueError("报告必须声明非刷机、未读取内存内容")
    refs = source.get("regions", [])
    if not refs or len({r.get("name") for r in refs}) != len(refs):
        raise ValueError("无效或重复的主线内存区域")
    for ref in refs:
        if number(ref["size"]) == 0:
            raise ValueError("主线区域尺寸为零")
        if number(ref["base"]) + number(ref["size"]) > 1 << 64:
            raise ValueError("主线区域越过 uint64")
    if not isinstance(report.get("regions"), dict):
        raise ValueError("设备区域列表缺失")


def segments(report):
    result = []
    for node, item in report["regions"].items():
        if item.get("status") == "unreadable":
            continue
        if item.get("status") != "observed":
            raise ValueError(f"未知设备区域状态: {node}")
        if not item.get("ranges"):
            raise ValueError(f"空 reg 列表: {node}")
        for region in item["ranges"]:
            base, size = number(region["base"]), number(region["size"])
            if size <= 0 or base + size > 1 << 64:
                raise ValueError(f"设备区域长度错误: {node}")
            if region.get("bytes") != size:
                raise ValueError(f"解析长度与 bytes 不一致: {node}")
            result.append({"node": node, "base": base, "end": base + size, "size": size})
    return sorted(result, key=lambda x: (x["base"], x["end"]))


def overlapping(entries):
    # Sweep sorted intervals, does not treat adjacent end=start as overlapping.
    collisions = []
    for i, a in enumerate(entries):
        for b in entries[i + 1:]:
            if b["base"] >= a["end"]:
                break
            if b["base"] < a["end"] and a["base"] < b["end"]:
                collisions.append([a["node"], b["node"]])
    return collisions


def compare(source, report):
    validate(source, report)
    active = segments(report)
    collisions = overlapping(active)
    by_name = {}
    for reg in active:
        by_name.setdefault(reg["node"], []).append(reg)
    changes = []
    for ref in source["regions"]:
        base, size = number(ref["base"]), number(ref["size"])
        other = []
        for x in active:
            if base < x["end"] and x["base"] < base + size and x["node"] != ref.get("observed_node"):
                other.append({"live_node": x["node"],
                              "overlap_bytes": min(base + size, x["end"]) - max(base, x["base"])})
        matches = by_name.get(ref.get("observed_node"), []) if ref.get("observed_node") else []
        if not ref.get("observed_node") or not matches:
            state = "unmapped_or_unread"
        elif len(matches) != 1:
            state = "multiple_live_ranges"
        elif base == matches[0]["base"] and size == matches[0]["size"]:
            state = "same"
        else:
            state = "different"
        changes.append({
            "name": ref["name"], "mainline_base": ref["base"], "mainline_size": ref["size"],
            "live_node": ref.get("observed_node"), "state": state,
            "live_ranges": [
                {"base": f"0x{m['base']:x}", "size": f"0x{m['size']:x}"}
                for m in matches
            ],
            "mainline_overlaps_other_live_regions": other,
        })
    return {
        "phase": "P0b-reg-compare", "device": "umi",
        "upstream_commit": source["source"]["commit"],
        "observed_regions": len(active),
        "total_observed_bytes": sum(x["size"] for x in active),
        "live_internal_overlaps": collisions,
        "comparison": changes,
        "safe_to_flash": False,
        "linux_612_boot_verified": False,
        "scope": "14 selected live nodes vs 18 upstream SoC defaults; incomplete board-level evidence",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", required=True, type=Path)
    p.add_argument("--baseline", type=Path, default=BASELINE)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    try:
        source = json.loads(args.baseline.read_text(encoding="utf-8"))
        report = json.loads(args.report.read_text(encoding="utf-8"))
        result = compare(source, report)
        output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(output, encoding="utf-8")
            print(f"已生成只读比对报告: {args.output}")
        else:
            print(output)
        return 0 if not result["live_internal_overlaps"] else 2
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"内存对照失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
