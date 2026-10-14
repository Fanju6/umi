#!/usr/bin/env bash
# 只读预检：不会刷机、不获取 root、不修改系统分区。
set -Eeuo pipefail

if ! command -v adb >/dev/null 2>&1; then
  echo '未找到 adb（请安装 Android platform-tools）。' >&2
  exit 2
fi
state="$(adb get-state 2>/dev/null || true)"
if [[ "$state" != "device" ]]; then
  echo '请通过 USB 调试授权并确保只连接一台 Android 设备。' >&2
  exit 2
fi

get_prop() { adb shell getprop "$1" | tr -d '\r\n'; }
device="$(get_prop ro.product.device)"
vendor="$(get_prop ro.product.vendor.device)"
if [[ "$device" != "umi" && "$vendor" != "umi" ]]; then
  echo "设备不是 umi (product=$device vendor=$vendor)，拒绝继续。" >&2
  exit 3
fi

echo '=== Xiaomi Mi 10 umi / 只读预检 ==='
printf '设备: %s\n' "$device"
printf 'Android API: %s\n' "$(get_prop ro.build.version.sdk)"
printf 'Android release: %s\n' "$(get_prop ro.build.version.release)"
printf 'LineageOS: %s\n' "$(get_prop ro.lineage.version)"
printf '内核: %s\n' "$(adb shell uname -r | tr -d '\r\n')"
printf 'SELinux: %s\n' "$(adb shell getenforce | tr -d '\r\n')"
printf '槽位: %s\n' "$(get_prop ro.boot.slot_suffix)"
printf 'Verified Boot: %s\n' "$(get_prop ro.boot.verifiedbootstate)"

echo '=== 只检查分区链接是否存在（不读取分区字节） ==='
adb shell 'for p in boot vendor_boot init_boot dtbo vbmeta recovery; do
  if [ -e /dev/block/by-name/"$p" ]; then
    echo "$p: exists"
  else
    echo "$p: not found"
  fi
done'

echo '=== 预检结束 ==='
echo '本工具不会运行 su、setenforce、fastboot、dd 或任何系统写入命令。'
echo '该结果不证明 boot.img 安全或 KernelSU 在真机上已通过。'
