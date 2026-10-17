#!/usr/bin/env python3
"""umi P0b 只读设备事实采集：仅执行白名单 adb shell 命令，不需要 Root。

不读取 IMEI、Android ID、MAC、序列号、/proc/cmdline、全量 getprop、原始 FDT、块设备内容。
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

SECTIONS = (
    "device", "model", "android", "lineage", "kernel", "boot_complete",
    "slot_suffix", "ab_update", "selinux", "dt_model", "dt_compatible",
    "dt_reserved_names", "partition_names", "ufs_hosts", "usb_platforms",
    "regulator_names", "i2c_component_names",
)
START = "__UMI_P0B_"
END = "__UMI_P0B_END__"
MAX_PER_SECTION = 16000

# 注意只读：没有 su、dd、flash、mount、写 sysfs 等操作。
DEVICE_SCRIPT = r"""
section() { printf '\n__UMI_P0B_%s__\n' "$1"; }
section device; getprop ro.product.device
section model; getprop ro.product.model
section android; getprop ro.build.version.release
section lineage; getprop ro.lineage.version
section kernel; uname -r
section boot_complete; getprop sys.boot_completed
section slot_suffix; getprop ro.boot.slot_suffix
section ab_update; getprop ro.build.ab_update
section selinux; getenforce
DT=""
for root in /sys/firmware/devicetree/base /proc/device-tree; do
  if [ -d "$root" ]; then DT="$root"; break; fi
done
section dt_model
if [ -r "$DT/model" ]; then tr '\000' '\n' < "$DT/model"; fi
section dt_compatible
if [ -r "$DT/compatible" ]; then tr '\000' '\n' < "$DT/compatible"; fi
section dt_reserved_names
if [ -d "$DT/reserved-memory" ]; then
  for node in "$DT"/reserved-memory/*; do [ -d "$node" ] && printf '%s\n' "${node##*/}"; done
fi
section partition_names
for root in /dev/block/by-name /dev/block/bootdevice/by-name /dev/block/platform/soc/1d84000.ufshc/by-name; do
  if [ -d "$root" ]; then
    for node in "$root"/*; do [ -e "$node" ] && printf '%s\n' "${node##*/}"; done
    break
  fi
done
section ufs_hosts
for node in /sys/class/ufs/*; do [ -e "$node" ] && printf '%s\n' "${node##*/}"; done
section usb_platforms
for node in /sys/bus/platform/devices/*; do
  [ -e "$node" ] || continue
  case "${node##*/}" in *dwc3*|*a600000*|*a6f8800*|*usb-phy*|*88e3000*) printf '%s\n' "${node##*/}" ;; esac
done
section regulator_names
i=0
for node in /sys/class/regulator/regulator*/name; do
  [ -r "$node" ] || continue
  name=$(cat "$node" 2>/dev/null)
  case "$name" in *l5*|*l6*|*l9*|*l17*|*s4*|*ufs*|*vdd*|*rpmh*) printf '%s\n' "$name"; i=$((i+1));; esac
  [ "$i" -ge 80 ] && break
done
section i2c_component_names
i=0
for node in /sys/bus/i2c/devices/*/name; do
  [ -r "$node" ] || continue
  name=$(cat "$node" 2>/dev/null)
  case "$name" in *fts*|*goodix*|*bq*|*p9415*|*rx1619*|*ln8282*|*cs35*|*smb*) printf '%s\n' "$name"; i=$((i+1));; esac
  [ "$i" -ge 40 ] && break
done
printf '\n__UMI_P0B_END__\n'
"""


def parse_sections(stdout: str) -> dict[str, list[str]]:
    current = None
    values: dict[str, list[str]] = {}
    seen_end = False
    for raw in stdout.replace("\r", "").split("\n"):
        line = raw.strip()
        if line == END:
            seen_end = True
            break
        if line.startswith(START) and line.endswith("__"):
            key = line[len(START):-2]
            if key not in SECTIONS or key in values:
                raise ValueError(f"异常采集段：{key}")
            current = key
            values[key] = []
        elif current is not None and line:
            if sum(len(x) + 1 for x in values[current]) + len(line) > MAX_PER_SECTION:
                raise ValueError("设备输出长度超过采集上限")
            values[current].append(line)
    if not seen_end or set(values) != set(SECTIONS):
        raise ValueError("ADB 输出不完整，请检查连接或权限；不要将半成品当成有效报告")
    return values


def build_report(values: dict[str, list[str]]) -> dict:
    if values["device"] != ["umi"]:
        raise ValueError(f"仅支持 umi，实际设备标识：{values['device']!r}")
    one = ("device", "model", "android", "lineage", "kernel", "boot_complete",
           "slot_suffix", "ab_update", "selinux", "dt_model")
    report = {key: (values[key][0] if values[key] else None) for key in one}
    for key in SECTIONS:
        if key not in one:
            # 物料、设备树的列表为空意味着未知/不可读，绝不代表组件不存在。
            report[key] = sorted(set(values[key]))
    report.update({
        "schema_version": 1,
        "phase": "P0b",
        "source": "adb shell unprivileged readonly",
        "safe_to_flash": False,
        "first_boot_test": False,
        "limitations": "未读取原始 DTB/reg 属性、未检查实际寄存器范围；空列表含义未知（未观察到/权限不足），并非硬件缺失",
    })
    return report


def probe(adb: str) -> dict:
    r = subprocess.run(
        [adb, "shell", "sh"],
        input=DEVICE_SCRIPT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=40, check=False,
    )
    if r.returncode:
        raise RuntimeError(f"ADB 命令失败（退出码 {r.returncode}），请确认 adb devices 只有一个在线设备")
    return build_report(parse_sections(r.stdout))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--adb", default="adb", help="ADB 程序位置，默认 PATH 中的 adb")
    p.add_argument("--output", type=Path, help="可选：写入脱敏 JSON 报告文件")
    args = p.parse_args()
    try:
        report = probe(args.adb)
        result = json.dumps(report, indent=2, ensure_ascii=False)
        if args.output:
            args.output.write_text(result + "\n", encoding="utf-8")
            print(f"只读 P0b 报告已生成：{args.output}")
        else:
            print(result)
        return 0
    except (OSError, subprocess.TimeoutExpired, ValueError, RuntimeError) as exc:
        print(f"P0b 采集失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
