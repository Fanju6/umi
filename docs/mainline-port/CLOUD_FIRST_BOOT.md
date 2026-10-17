# umi Linux 6.12：纯 GitHub Actions 云端构建完整 Boot v2 实验候选

**2026-10-17：按项目要求改为 CI 自动构建，不要求用户在 Windows 上打包。**

使用 .github/workflows/mainline-cloud-firstboot.yml。每次 PR 触发或者人工 workflow_dispatch：

1. 在 GitHub Ubuntu runner 克隆锁定 SHA adc218676eef25575469234709c2d87185ca223a 的 torvalds/linux v6.12，交叉编译 ARM64 Image；开启 RAM/initrd、Pstore/Ramoops 基本配置和主要 Qualcomm UFS regulator driver。这一步是完整内核构建，而不只 DTS 语法检测。
2. 同一个 job 使用该 Linux 6.12 DTS headers 编译 umi P1n 实验 DTB，检查 qcom,msm-id=<356 0x10000>、qcom,board-id=<43 0>、Ramoops 0xB0000000/4MiB，以及 UFS/USB 和未完全验证的 PMIC provider 继续 disabled。
3. 下游 boot job 下载同一 workflow 的 Image/DTB artifact，静态交叉编译 ARM64 最小 PID1、构造 RAM-only cpio.gz，生成有 UMI612-MINIMAL-INIT 日志标记的 initramfs。
4. **CI 自动下载固定原版 Boot**：https://mirrorbits.lineageos.org/full/umi/20261004/boot.img；用既有旧 KernelSU CI 锁定的 SHA-256 ce4a917a9233921b03e748b1fffc7b5ecea613c7ddf72208f26c77189f31a693 校验。如果链接无效或 hash 不匹配，CI 必须失败；不能悄悄换另一版 ROM。
5. 从 upstream LineageOS lineage-23.0 mkbootimg/unpack_bootimg 与 avbtool 解包 / 重新封装 Android Boot Header v2。将 kernel、ramdisk、DTB 一次性替换；保留原始地址、board、OS version、必要的原始 cmdline（增加 rdinit=/init）；如原版含 unsigned AVB hash footer，则使用原属性生成新的 NONE/sha256 footer。
6. 实际重新解析输出 boot.img，核查 size <= 134217728 B、header v2、page 4096、boot load address 五项、各 section SHA-256、AVB props、cmdline 和输出文件 SHA256。
7. 成功后统一上传 artifact：**umi-Linux612-CLOUD-Boot-v2-LAB-UNVERIFIED**；包括 cloud candidate boot.img、initramfs、boot-validation.json、SHA256SUMS、README-FIRST.txt。另一 artifact 保存内核和 DTB 源产物以便定位。

## 绝不能混淆的 Boot 基线

此前用户实际运行的 Root/KernelSU Boot 只读备份 SHA-256 为 2bb0cabcd7bf996cc0053ce9f44248d1ec59c3b583b3259a0343f2ef6544c3b7。它**不是** CI 下载的公开官方 Boot 的 SHA-256 ce4a917a9233921b03e748b1fffc7b5ecea613c7ddf72208f26c77189f31a693。因此 CI 产物不是在用户原始 KernelSU Boot 上改装，也不能声称与私有当前 Boot 的全部命令行、DTB 和 AVB 属性相同。需要兼容性验证与真实机测试。用户只需要通过 GitHub Actions 获取生成产物；**无须向 CI 上传私人 boot.img，也无须本机安装 mkbootimg。**

## 仍然只是可供实验的 Boot，不等于 Android ROM

首次测试不要求 UFS、USB、WiFi、屏幕或 Android 运行。其唯一目标是证明 Linux 6.12 的早期执行以及最小静态 /init 的 Pstore 记录。需要实际 Bootloader 选择适当的 DTB；两个厂家私有 UFS 电源投票、PM8150 输入 parent 都尚未确认，研究 provider/UFS/USB 仍禁用。这种实验 boot.img 的 CI 静态结构通过不等于真机成功进入内核，不证明可以启动 Android，或失败后 TWRP 一定能读到失败时日志。

刷入前：用户已经声明有独立 REC/TWRP，并能通过 ADB 读取日志；仍应确认能用按键进 Recovery、能恢复本机备份 boot.img。非 A/B，先只测试 Boot，不改 Recovery/DTBO/VBMeta/Super/Userdata。脚本没有、GitHub runner 也没有直接接触或写入用户手机。

首次失败返回 TWRP 后通过 scripts/mainline_recovery_postmortem.py 只读收集 pstore；Recovery 自己的 dmesg 不等于前一个失败内核的 dmesg。Pstore 是否跨重启保留尚未知。

当前：研究 PR #8 Open，main 原始 KernelSU 4.19 不变，刷机前需要检查具体 artifact CI 结论及可逆恢复条件。云端已提供打包执行流程，无需人工复制各组件并运行本地 packer。
