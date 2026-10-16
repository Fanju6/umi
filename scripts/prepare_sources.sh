#!/usr/bin/env bash
# Pull fixed upstream revisions, wire official KernelSU into the umi kernel.
# This is a source-integration step, NOT an assertion that the kernel boots.
set -Eeuo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=../config/upstream.env
source "$repo_root/config/upstream.env"
workdir="${1:-$repo_root/.work}"
mkdir -p "$workdir"
workdir="$(cd "$workdir" && pwd)"

clone_locked() {
  local url="$1" ref="$2" pin="$3" destination="$4"
  if [[ ! -d "$destination/.git" ]]; then
    git clone --depth 1 --filter=blob:none --branch "$ref" "$url" "$destination"
  fi
  if [[ "$(git -C "$destination" rev-parse HEAD)" != "$pin" ]]; then
    git -C "$destination" fetch --depth 1 origin "$pin"
    git -C "$destination" -c advice.detachedHead=false checkout --detach "$pin"
  fi
  [[ "$(git -C "$destination" rev-parse HEAD)" == "$pin" ]] || {
    echo "源代码版本与锁定的 SHA 不一致：$destination" >&2
    exit 1
  }
}

clone_locked "$LINEAGE_KERNEL_REPO" "$LINEAGE_KERNEL_REF" "$LINEAGE_KERNEL_SHA" "$workdir/kernel"
clone_locked "$KSU_REPO" "$KSU_REF" "$KSU_SHA" "$workdir/KernelSU"

kernel="$workdir/kernel"
ksu="$workdir/KernelSU"
if [[ -e "$kernel/drivers/kernelsu" && ! -L "$kernel/drivers/kernelsu" ]]; then
  echo "驱动目录已存在且不是软链接，拒绝覆盖。" >&2
  exit 1
fi
ln -sfn ../../KernelSU/kernel "$kernel/drivers/kernelsu"

if ! grep -Fq 'source "drivers/kernelsu/Kconfig"' "$kernel/drivers/Kconfig"; then
  printf '\nsource "drivers/kernelsu/Kconfig"\n' >> "$kernel/drivers/Kconfig"
fi
if ! grep -Fq 'obj-$(CONFIG_KSU) += kernelsu/' "$kernel/drivers/Makefile"; then
  printf '\nobj-$(CONFIG_KSU) += kernelsu/\n' >> "$kernel/drivers/Makefile"
fi
config="$kernel/arch/arm64/configs/vendor/xiaomi/umi.config"
if ! grep -Eq '^CONFIG_KSU=y$' "$config"; then
  cat >> "$config" <<'EOF'

# Official KernelSU integration for umi (pinned upstream; review required)
CONFIG_KPROBES=y
CONFIG_KRETPROBES=y
CONFIG_KSU=y
# CONFIG_KSU_DEBUG is not set
EOF
fi

printf 'LineageOS kernel: %s\n' "$(git -C "$kernel" rev-parse HEAD)"
printf 'KernelSU:          %s\n' "$(git -C "$ksu" rev-parse HEAD)"
echo "Integrated sources: $workdir"
echo "提示：这是尚未应用全部 4.19 兼容补丁的初始源码；后续必须完成补丁、构建和审计。"
