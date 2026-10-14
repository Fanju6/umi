#!/usr/bin/env bash
# Diagnostic kernel compilation; this does not assemble a flashable boot.img.
set -Eeuo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
workdir="$repo_root/.work"
mode="baseline"
if [[ "$#" -ge 1 ]]; then mode="$1"; fi
if [[ "$#" -ge 2 ]]; then workdir="$2"; fi
[[ "$mode" == "baseline" || "$mode" == "ksu" ]] || { echo "用法: $0 baseline|ksu [workdir]" >&2; exit 2; }
kernel="$workdir/kernel"
out="$workdir/output-$mode"
mkdir -p "$out"
out="$(cd "$out" && pwd)"
[[ -d "$kernel" ]] || { echo "请先执行 scripts/prepare_sources.sh" >&2; exit 1; }

# Clang 18 is an exploratory baseline; the final build must pin the actual
# toolchain of the installed LineageOS release.
build_args=(
  O="$out" ARCH=arm64
  CC=clang-18 LD=ld.lld-18 AR=llvm-ar-18 NM=llvm-nm-18
  OBJCOPY=llvm-objcopy-18 STRIP=llvm-strip-18
  CROSS_COMPILE=aarch64-linux-gnu-
  CROSS_COMPILE_COMPAT=arm-linux-gnueabi-
  LLVM_IAS=1
)
make -C "$kernel" "${build_args[@]}" vendor/kona-perf_defconfig
fragments=(
  "$kernel/arch/arm64/configs/vendor/debugfs.config"
  "$kernel/arch/arm64/configs/vendor/xiaomi/sm8250-common.config"
)
if [[ "$mode" == "baseline" ]]; then
  # Merge the untouched umi fragment from the pinned original revision.
  git -C "$kernel" show HEAD:arch/arm64/configs/vendor/xiaomi/umi.config > "$workdir/original-umi.config"
  fragments+=("$workdir/original-umi.config")
else
  fragments+=("$kernel/arch/arm64/configs/vendor/xiaomi/umi.config")
fi
bash "$kernel/scripts/kconfig/merge_config.sh" -m -O "$out" "$out/.config" "${fragments[@]}"
if [[ "$mode" == "baseline" ]]; then
  "$kernel/scripts/config" --file "$out/.config" --disable KSU
fi
make -C "$kernel" "${build_args[@]}" olddefconfig
echo "KernelSU config: $(grep -E '^CONFIG_KSU=|^# CONFIG_KSU is not set' "$out/.config" || true)"
echo "CLANG: $(clang-18 --version | head -1)"
make -C "$kernel" "${build_args[@]}" -j2 Image dtbs
echo "诊断编译完成：$out/arch/arm64/boot/Image"
echo "注意：还未生成 boot.img，也没有经过真机验证。"
