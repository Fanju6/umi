> **历史 TEST2 阶段说明：** 下文记录当时尚未真机验收的阶段。官方 KernelSU v3.3.0 TEST2 此后已完成真机开机、Root、授权隔离与重启测试；本文件仍只用于 TEST2 工作流历史触发，不代表当前 v3.3.1 的使用状态。

# Xiaomi Mi 10 umi · 官方 KernelSU 3.3.0 实验性 boot.img 构建

**实验风险：内核已经编译成功，但从未在当前 Android 16 真机启动。SELinux、SID/AVC、Manager/Seccomp 仍未通过运行时验收。实验可能导致设备无法启动，且无法保证恢复过程没有数据损失。**

本工作流使用用户当前相同的 LineageOS `23.2-20261004-NIGHTLY-umi` 官方原版 boot.img：
https://mirrorbits.lineageos.org/full/umi/20261004/boot.img

已由只读 CI #38566227406 核实：
- 原版 SHA256：`ce4a917a9233921b03e748b1fffc7b5ecea613c7ddf72208f26c77189f31a693`
- Boot Header v2；4KiB page，128MiB 大小。
- 原版 Ramdisk 1,494,000 字节，DTB 1,424,944 字节；必须保持它们 SHA-256 不变。
- AVB Footer：`Algorithm NONE`、Hash sha256、分区 boot；原版携带 Android 16 和构建指纹属性。

新 CI `.github/workflows/experimental-boot.yml`：
1. 从 pinned LineageOS 与官方 KernelSU v3.3.0 重新编译完整内核。
2. 校验下载的原版 SHA-256；调用 LineageOS 的 unpack_bootimg/mkbootimg 保留原版 Ramdisk/DTB/启动参数，替换 Kernel。
3. 重建 AVB Hash Footer（算法 NONE，重新计算摘要），保留同版 fingerprint、Android 版本、原 boot 分区尺寸。
4. 自动比较原版/实验版 Kernel、Ramdisk、DTB、Header、cmdline、AVB 字段；任何不匹配都不上传镜像。
5. 严格校验通过后，将临时 `EXPERIMENTAL-UNVERIFIED` ZIP 保存于 Actions Artifacts，**不会刷机、不会发布 Releases**。

重要：`safe_to_flash=false` 始终保留，即使镜像结构验证通过。ROM 运行时、SELinux 强制模式及 KernelSU Manager 均尚未验证。实验前须准备完全匹配的原版 boot.img、确认 Fastboot/Recovery 能访问，并对个人数据做备份；**用户拥有解锁 Bootloader 并不代表所有失败都必然无损恢复。**

## 2026-10-15：第二版测试镜像（Hook-Fix / TEST2）

这次运行是在上次第一阶段 init 失败（pstore 证实 syscall table 写入失败，但 dispatcher 假装安装成功）的基础上制作的**受控对照实验**。

唯一的内核差异来源：原版 LineageOS 23.2 umi 同一源码、原版 Ramdisk/DTB/Boot Header/AVB Hash Footer、不改变 Clang18 工具链；仅新增：

- `UMI_KSU_419_DISPATCHER_FAIL_CLOSED`：sys_call_table 写入失败时，不启用 sys_enter 重定向，也不把失败 Hook 记为已安装。
- `UMI_KSU_419_ARM64_BLOCK_WALK`：4.19 ARM64 的 PMD/PUD section 映射处理必须先于 `pmd_bad`/`pud_bad`，修复原先无法解析 `sys_call_table[42]` 物理地址的问题。

验证范围：最新源码与驱动/整核的 CI 已通过；本次会**重新完整构建、按官方 boot.img 重包并保留 RAMDISK/DTB 哈希，自动验证原版配置与 AVB Footer**，只有全项通过才上传 `UMI-TEST2-HOOKFIX-UNVERIFIED-KernelSU3.3.0-boot` 附件。每份压缩包包含 `PROVENANCE`、SHA-256 与严格验证 JSON。Workflow 仅因手动 dispatch 或此显式触发文档变化而运行，不在其他代码提交时自动打包。

风险：**本版尚未真机启动验证，不代表可以日常刷入。** 若用户进行自愿复测，先保证当前 ROM 原版 boot.img 可立即恢复、数据已备份，并且 Recovery ADB 的 `/sys/fs/pstore/console-ramoops-0` 可以导出（此前已验证）。失败后尽量先 Recovery 导出 pstore，再恢复原版 boot.img；不要反复重启覆盖诊断信息。回传日志只在本地或聊天上传，不要把包含敏感信息的原始日志上传到公开仓库。

验收标准有两个独立阶段：

1. **能开机**：至少运行到 Android Launcher，`adb shell getenforce` 仍是 Enforcing；`uname -r` 证实是实验内核，而不是原版。
2. **能 Root**：KernelSU Manager 实际识别并授权，基本文件访问和 SELinux 隔离正常；即便第一阶段成功，第二阶段仍可能不通过。

两个阶段未全部验证前，继续按未验证实验版处理，不公开发布 Release。
