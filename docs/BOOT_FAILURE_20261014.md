# 2026-10-14 · umi 实验 KernelSU boot.img 启动失败

## 已确认

- 机型：Xiaomi Mi 10 `umi`，Android 16 / LineageOS `23.2-20261004-NIGHTLY-umi`，非 A/B 布局。
- 官方 KernelSU 3.3.0 实验镜像：CI #38567509103 生成；SHA256 `b5701bb8347ea4d37c584b96eedd00f6e51d867aa9a68ec21d75a16f85ae2aaf`。
- 实验镜像静态检查（Boot Header v2、原 Ramdisk/DTB、AVB Hash Footer）全通过，但**真机无法启动**。
- 使用官方原版 `boot.img` 恢复成功。实验版正式标记为 `KNOWN_BOOT_FAILURE`，不得作为已可刷版本推广。

## 目前未证实

尚不清楚失败发生在 Bootloader、内核初始化、第一阶段 init、SELinux policy 初始化/重载、或第二阶段 init / Zygote。此前采用 Clang18 的试验工具链，且没有完成**同一工具链构建的干净非 KSU 内核**的启动基线测试，因此不能简单归因于 KernelSU。

## 下一轮调查（严禁直接重复刷原文件）

1. 利用已恢复开机的原版系统只读检查 `/sys/fs/pstore` 是否还有上一次失败的 `console-ramoops` 或 `dmesg-ramoops`；部分设备权限受限或重启后覆盖，缺失不等于没有内核 panic。
2. 只读获取 `ro.boot.bootreason`、`sys.boot.reason`、`/proc/version`，根据是否有上一轮 kernel pstore 来确定启动阶段。
3. 离线对照官方原版 boot.img 内嵌 IKCONFIG 与 CI 构建 `.config`；需要区分 Clang/LTO/CFI/设备配置问题与内核源码改动。
4. 若仍无法定位，再构建不含 KernelSU 的同工具链基线以比较（不得把未经测试的基线镜像宣传成安全版）。
5. 单独审查早期 KSU init hook、4.19 的 SELinux policydb 更新与 Android 16 第二阶段 init 顺序，补上失败回滚和保守禁用条件。

**即使后来 CI 再次绿色，也不能覆盖真实失败事实。** 除非有真机启动成功且功能正常的证据，所有实验镜像均为不可证实安全的调试产物。
