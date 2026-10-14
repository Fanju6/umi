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
# Linux 4.19's LLVM build internally calls unversioned llvm-* tools.
export PATH="/usr/lib/llvm-18/bin:$PATH"
for tool in clang-18 ld.lld-18 llvm-ar llvm-nm llvm-objcopy llvm-strip; do
  command -v "$tool" >/dev/null || { echo "缺少 LLVM 工具: $tool" >&2; exit 1; }
done


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
if [[ "$mode" == "ksu" ]]; then
  # Fast single-object compile to surface the first KernelSU ABI error.
  # KernelSU includes SELinux's generated flask.h through objsec.h.
  # Normal full builds generate it as part of SELinux; driver-only builds must
  # request it explicitly before compiling the KernelSU directory.
  # This 4.19 top-level Makefile does not accept the generated header as
  # a direct target. Building the parent Kbuild directory generates it.
  make -C "$kernel" "${build_args[@]}" -j4 security/selinux/
  # Kbuild 4.19 supports a directory target, not an individual subdir object.
  make -C "$kernel" "${build_args[@]}" -j4 drivers/kernelsu/
  if [[ "${KERNEL_QUICK:-0}" == "1" ]]; then
    echo "KernelSU driver-only diagnostic completed; full kernel not built."
    exit 0
  fi
fi
make -C "$kernel" "${build_args[@]}" -j4 Image dtbs
python3 "$repo_root/scripts/check_build_output.py" "$mode" "$out"
echo "诊断编译完成：$out/arch/arm64/boot/Image"
echo "注意：还未生成 boot.img，也没有经过真机验证。"
