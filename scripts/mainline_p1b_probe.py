#!/usr/bin/env python3
"""Collect read-only PMIC/UFS and Type-C evidence from umi using ordinary adb shell."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MARK = "__UMI_P1B__"
END = "__UMI_P1B_END__"
ATTR = {
    "regulator": ("name", "microvolts", "state", "min_microvolts", "max_microvolts"),
    "typec": ("data_role", "power_role", "port_type", "preferred_role"),
    "usb_role": ("role",),
    "usb_supply": ("type", "usb_type", "online", "voltage_max", "current_max"),
    "ufs": ("status",),
}
KEY = {
    "regulator": re.compile(r"regulator[0-9]+"),
    "typec": re.compile(r"port[0-9]+"),
    "usb_role": re.compile(r"[A-Za-z0-9_.:@-]{1,70}"),
    "usb_supply": re.compile(r"(usb|usbpd|usb_pd|pc_port|main)"),
    "ufs": re.compile(r"[A-Za-z0-9_.:@-]{1,70}"),
}
RELEVANT = re.compile(r"pm8150|ufs|vreg|bob|l2|l5|l6|l9|l12|l17|s4", re.I)

SCRIPT = r"""
printf '__UMI_P1B__|device|umi|id|%s\n' "$(getprop ro.product.device)"
read_field() {
  cls="$1"; id="$2"; prop="$3"; file="$4"
  if [ ! -e "$file" ]; then value=missing
  elif [ ! -r "$file" ]; then value=unreadable
  else value=$(cat "$file" 2>/dev/null) || value=unreadable
  fi
  printf '__UMI_P1B__|%s|%s|%s|%s\n' "$cls" "$id" "$prop" "$value"
}
count=0
for node in /sys/class/regulator/regulator[0-9]*; do
  [ -r "$node/name" ] || continue
  label=$(cat "$node/name" 2>/dev/null) || continue
  case "$label" in *pm8150*|*ufs*|*vreg*|*bob*|*l2*|*l5*|*l6*|*l9*|*l12*|*l17*|*s4*)
    id=$(basename "$node")
    for prop in name microvolts state min_microvolts max_microvolts; do
      read_field regulator "$id" "$prop" "$node/$prop"
    done
    count=$((count+1)); [ "$count" -ge 128 ] && break
  ;; esac
done
count=0
for node in /sys/class/typec/port[0-9]*; do
  [ -d "$node" ] || continue
  id=$(basename "$node")
  for prop in data_role power_role port_type preferred_role; do
    read_field typec "$id" "$prop" "$node/$prop"
  done
  count=$((count+1)); [ "$count" -ge 8 ] && break
done
count=0
for node in /sys/class/usb_role/*; do
  [ -d "$node" ] || continue
  id=$(basename "$node")
  read_field usb_role "$id" role "$node/role"
  count=$((count+1)); [ "$count" -ge 8 ] && break
done
for id in usb usbpd usb_pd pc_port main; do
  node="/sys/class/power_supply/$id"
  [ -d "$node" ] || continue
  for prop in type usb_type online voltage_max current_max; do
    read_field usb_supply "$id" "$prop" "$node/$prop"
  done
done
count=0
for node in /sys/bus/platform/devices/*1d84000* /sys/class/ufs/*; do
  [ -e "$node" ] || continue
  id=$(basename "$node")
  read_field ufs "$id" status "$node/status"
  count=$((count+1)); [ "$count" -ge 8 ] && break
done
printf '__UMI_P1B_END__\n'
"""


def parse(output):
    groups = {key: {} for key in ATTR}
    seen = set()
    identity = None
    completed = False
    for lineno, row in enumerate(output.replace("\r", "").splitlines()):
        if row == END:
            completed = True
            break
        if not row:
            continue
        parts = row.split("|", 4)
        if len(parts) != 5 or parts[0] != MARK or lineno > 1500:
            raise ValueError("非白名单采集行或输出过长")
        _, cls, ident, prop, value = parts
        if len(value) > 180 or not value.isprintable() or (cls, ident, prop) in seen:
            raise ValueError("无效或重复的设备属性")
        seen.add((cls, ident, prop))
        if cls == "device":
            if ident != "umi" or prop != "id" or identity is not None:
                raise ValueError("无法确认设备 ID")
            identity = value
            continue
        if cls not in ATTR or not KEY[cls].fullmatch(ident) or prop not in ATTR[cls]:
            raise ValueError("未知采集路径或属性")
        groups[cls].setdefault(ident, {})[prop] = value
    if not completed or identity != "umi":
        raise ValueError("不是完整的 umi 采集结果")
    for cls, nodes in groups.items():
        for ident, props in nodes.items():
            if set(props) != set(ATTR[cls]):
                raise ValueError(f"{cls}/{ident} 采集属性不完整")
    groups["regulator"] = {
        key: data for key, data in groups["regulator"].items()
        if RELEVANT.search(data.get("name", ""))
    }
    return {
        "schema_version": 1, "device": "umi", "phase": "P1b",
        "source": "non-root adb shell read-only sysfs",
        "writes_performed": False, "safe_to_flash": False,
        "groups": groups,
        "summary": {cls: len(items) for cls, items in groups.items()},
        "limitations": "空列表/缺失属性可能是权限或旧内核 sysfs 差异；运行时电压不代表允许设置的安全值",
    }


def collect(adb):
    r = subprocess.run([adb, "shell", "sh"], input=SCRIPT, text=True,
                       capture_output=True, timeout=75, check=False)
    if r.returncode:
        raise RuntimeError(f"ADB shell 失败，退出码 {r.returncode}")
    return parse(r.stdout)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--adb", default="adb")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    try:
        report = collect(a.adb)
        data = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if a.output:
            a.output.write_text(data, encoding="utf-8")
            print(f"P1b 只读报告已保存：{a.output}")
            print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        else:
            print(data)
        return 0
    except (OSError, subprocess.TimeoutExpired, ValueError, RuntimeError) as e:
        print(f"P1b 采集失败：{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
