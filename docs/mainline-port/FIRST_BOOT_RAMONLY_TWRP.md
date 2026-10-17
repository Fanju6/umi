# umi Linux 6.12 首次启动实验：TWRP 后验取证 + RAM-only PID1

**2026-10-17。** 用户已明确说明在 umi 有独立 REC/TWRP，熟悉刷入与回退，并希望首轮失败后通过 Recovery ADB 读取日志。先前已在 PC 私有目录对 boot/recovery/dtbo 做完整只读备份；本阶段开始准备能够直接在内存里运行并留下日志标记的最小 Linux 6.12 实验，而不再重复旧系统硬件探针。

## 已实现的工程组成

1. research/mainline/mini-init.c：AArch64 静态 PID1，RAM-only initramfs 的 /init。不启动 Android，不访问 /dev/block 或 userdata，不联网、不改分区、不自动重启；仅挂载易失的 devtmpfs/proc/sysfs，持续向 /dev/kmsg 和 /dev/console 写入明确标记 UMI612-MINIMAL-INIT。
2. .github/workflows/mainline-mininit.yml：独立 CI 编译 aarch64-linux-gnu-gcc -static，并将 /init、/dev/console、/dev/null 打包为标准 cpio.gz；保留下载用的非刷机研发产物。这一小组件可以独立重建，不必重新编译 6.12 内核。
3. research/mainline/sm8250-xiaomi-umi-p1n.dts：从 P1m（UFS/USB/研究 PMIC provider 均 disabled）继承；在 reserved-memory 中定义 ramoops 0xB0000000 起、4 MiB。record-size=0、console-size=2 MiB、pmsg-size=2 MiB，照搬已实测的 Linux 4.19 RAM 区间和模块设置，不宣称跨重启一定保留记录。
4. .github/workflows/mainline-dts-compile.yml：使用固定 Linux 6.12 cpp+dtc/fdtget 验证 P1n ramoops 节点、属性、六个 UFS/USB disable status 和 regulator provider disabled；不尝试刷机。
5. scripts/mainline_recovery_postmortem.py：必须在 TWRP/Recovery **已经启动**时明确执行；它先确认 ADB uid 0 且 Recovery/TWRP，再读取已挂载 pstore 的 whitelisted 文件和可选 /proc/last_kmsg。原始日志仅存在用户 PC 私有目录；脱敏 JSON 只报告长度、SHA-256、是否看到 Linux 6.12 / 内核 panic / 自定义 PID1 标记。脚本不会执行 reboot、fastboot、mount 或修改手机分区。

## 首次失败后，恢复到 TWRP 的命令

进入 TWRP、连接电脑，确保 adb devices 能看到设备。若要记录实验失败，执行：

~~~powershell
cd C:\Users\fanju\umi-p0b
git pull --ff-only
python scripts/mainline_recovery_postmortem.py --probe --output "$env:USERPROFILE\Desktop\umi-recovery-summary.json" --raw-log-dir "$env:USERPROFILE\Desktop\umi-recovery-rawlogs"
~~~

仅需分享 umi-recovery-summary.json；包含内核启动日志的原始文件只保存在 PC，可在脱敏后按需分析。重要局限：TWRP 的 live dmesg 属于 Recovery 当前内核，不能直接用来证明前一次 6.12 是否启动；如果 pstore 未被 Recovery 挂载或内存跨重启不能保留，脚本可能得到零个有效失败日志。这种结果不等于实验内核没有执行任何代码。

## 待完成后才能打包可试启动镜像

- 固定源码的 6.12 ARM64 Image CI 成功；确认使用的是实际 Image，而非只编译 DTS。
- 使用用户**本机**原始 boot.img 的头部与 AVB/DTB 布局，按 Boot Header v2 打包；不能公开原始 Boot 镜像或依赖另一台设备的 boot.img。
- 将新的 static initramfs 与已验证 P1n DTB 组合；检查 boot.img 大小、地址、ramdisk、header、嵌入 DTB、AVB 属性，并明确是否需要 bootloader 的匹配 DTB ID。这一步在原始 boot dtb section 格式未被本地核实之前不得假设已经解决。
- 优先采用可信的临时启动；若采用 Boot-only 刷写测试，必须确认实际存在单独进入 TWRP 的路径，并准备本机备份 boot.img 的可回退操作。
- 不修改 recovery/dtbo/vbmeta/userdata；不把 Kernel Panic 或 RAM 区域内容保留当成理所当然。

## 与以往流程的变化

此前多轮 PMIC/UFS/DTBO 的只读取证已经停止。以后聚焦真正的 Linux 6.12 Image、可进入 /init 的最小 ramdisk、可信 Boot v2 包装，以及 TWRP ADB 的实验后证据。若尚未通过本轮编译和 Boot 结构验证，DTS/PID1 产物本身不构成刷机包。

**当前状态：** 尚未完成 6.12 首次真机启动；main 与稳定 4.19+KernelSU 不改变，研究 PR #8 继续独立。不会提前宣称能安全刷入。


## Boot v2 实验镜像：本地原始 Boot 打包器（不会向手机写入）

新增 scripts/mainline_pack_boot_v2_local.py。需要四个经过独立检查的输入：
- 用户 Windows 本地原始 umi-original-images/boot.img 与 umi-preflight.json（必须逐字节 SHA-256 一致，不能使用其他机型 ROM）。
- 固定 Linux 6.12 Actions 编译后的 Image.generic-arm64.NOT-FLASHABLE。
- 独立 Actions 生成的 umi612-minimal-initramfs.cpio.gz。
- 编译并校验后的 umi-P1n-ramoops-DTB-NOT-FLASHABLE 对应 DTB。

还需要本地已有的 LineageOS mkbootimg 工具目录与 avbtool.py。此前仓库 experimental-v331-boot.yml 已实际使用过同族工具的 unpack_bootimg --format mkbootimg --null、mkbootimg 和 avbtool add_hash_footer 工作流。新的工具仅在原始 Header v2 独立 DTB section 可读、Boot SHA 符合 preflight 且原始 AVB 算法可支持时工作；如果原始 Boot v2 的 dtb_size=0，**立即拒绝**，不会自行假定 Bootloader 会接受另一个 DTB 封装模式。工具不在原始 Boot 上覆盖写入、不输出旧 cmdline 或 fingerprint、不访问手机。

在 PowerShell 下载好三个 CI 产物并解压后，假设本地 tools 在 .work/mkbootimg 和 .work/avb，下方是**仅用于本地生成测试候选镜像**的命令。修改 kernel、ramdisk、DTB 三个参数为下载后的实际路径：

~~~powershell
cd C:\Users\fanju\umi-p0b
git pull --ff-only
python scripts/mainline_pack_boot_v2_local.py --stock "$env:USERPROFILE\Desktop\umi-original-images\boot.img" --preflight "$env:USERPROFILE\Desktop\umi-preflight.json" --kernel "$env:USERPROFILE\Desktop\Image.generic-arm64.NOT-FLASHABLE" --ramdisk "$env:USERPROFILE\Desktop\umi612-minimal-initramfs.cpio.gz" --dtb "$env:USERPROFILE\Desktop\umi-p1n-not-bootable.dtb" --mkbootimg-dir ".work\mkbootimg" --avbtool ".work\avb\avbtool.py" --output "$env:USERPROFILE\Desktop\umi612-Boot-only-LAB.img"
~~~

本脚本会校验 ARM64 Image magic、gzip/newc 里的明确测试 marker、umi P1n FDT identity、Boot 的原始 header 关键地址、输出 section 的 SHA-256 与分区大小。它可在检测到未支持的签名布局或缺失原始 DTB section 时拒绝打包。**打包结构通过与 Bootloader 真正接受主线 DTB 是两回事。** 测试前必须确认 TWRP 能从失败启动独立进入，并有原始 boot.img 的可靠回刷办法。所有 UFS/USB 尚未使能，任何由此生成的镜像不能作为 Android ROM 或日常使用内核。

固定厂商源码 Kona root qcom,msm-id=<356 0x10000> 与 umi overlay root qcom,board-id=<43 0> 已写入仅测试用 P1n DTS；不能借此宣称 Stock DTBO 一定能成功套用到主线 DTB。恢复模式是实验的回退路径，不是启动兼容性的证明。
