# umi · TEST2 KernelSU 3.3.0 受控真机启动复测

这份方案只适用 **Xiaomi Mi 10 (umi)**、`LineageOS 23.2-20261004-NIGHTLY-umi`、当前已解锁 Bootloader 且用户已验证原版 boot.img 能恢复、Recovery ADB 能读取 `/sys/fs/pstore/console-ramoops-0` 的同一设备。

## 核心待验证问题

第一版 `boot.img` 的失败并非早期 Kernel Panic。前一份 pstore 显示：

- `KernelSU: patch syscall 42 failed`；
- 分发器仍宣称 `dispatcher installed at slot 42`；
- Android 第一阶段 `init` 的 stat/fstab 路径返回 `ENOSYS`；
- 最终进入 Fastboot。

本版 (TEST2) 只在 KSU 内核代码中增加两项修复：

1. 当 ARM64 syscall table 分发器安装失败时保持 `ksu_dispatcher_nr = -1`，不把正常系统调用重定向至无效槽位。
2. Linux 4.19 ARM64 的 `pud_sect`、`pmd_sect` 要先于 `pud_bad`、`pmd_bad` 处理，用于解析 block mapping 物理地址。

**仍采用之前的 Clang 18 工具链**，避免一次引入多个影响因素。实验镜像不自动刷写、不发布 Release，不代表 Root、SELinux、Manager 功能已验证。

## 下载和核对

仅在 `.github/workflows/experimental-boot.yml` 全部成功、Artifact 实际存在且 `experimental-boot-verification.json` 中 `repack_structurally_verified=true` 时，才有可供自主实验的 TEST2 镜像。

名称：`UMI-TEST2-HOOKFIX-UNVERIFIED-KernelSU3.3.0-boot`

解压后的文件名：`umi-KernelSU3.3.0-20261004-TEST2-HOOKFIX-boot.img`。

确认包内 `experimental-boot.sha256` 与本地 PowerShell `Get-FileHash -Algorithm SHA256` 匹配；`experimental-PROVENANCE.txt` 的构建提交、原版 ROM 日期和 Kernel SHA 应与 CI 一致。

## 复测注意事项

- 确保保留**同版本原版 boot.img**。原版 SHA256：`ce4a917a9233921b03e748b1fffc7b5ecea613c7ddf72208f26c77189f31a693`。
- 用户事先备份个人数据；不要假设回刷 boot 必然能恢复所有类型的启动失败。
- 如 Fastboot 支持临时启动，应优先考虑非持久测试；不假定 umi 所有 bootloader 版本均支持该方式。
- 任何无法启动的情况下，尽可能先进入 Recovery（不要多次重启）并读取 pstore；原版 Recovery ADB 已被用户实际验证可用：

```powershell
adb devices
adb shell ls -la /sys/fs/pstore
adb pull /sys/fs/pstore "$env:USERPROFILE\Desktop\umi-test2-pstore"
```

- 不得在公开 Issue / PR 上传未经脱敏的完整内核日志。日志可能包含地址、系统状态或设备标识。

## 验收矩阵：必须区分「开机」与「Root」

| 结果 | 通过标准 | 备注 |
|---|---|---|
| 内核完成启动 | 设备不进入强制 Fastboot，启动动画及 Android 桌面正常 | 静态验证无法证明 |
| Android 版本与设备 | `adb shell getprop ro.product.device` 为 `umi`；`ro.lineage.version` 对应 20261004 | 防止混淆其他 ROM |
| Android 启动完成 | `adb shell getprop sys.boot_completed` 为 `1` | 第一阶段 init 已结束不等于完整开机 |
| SELinux | `adb shell getenforce` 为 `Enforcing` | 不通过降低 SELinux 解决 |
| 实验内核身份 | `adb shell uname -r` 和 `adb shell cat /proc/version` 证实使用新的实验构建 | 勿误将恢复原版的成功算成 TEST2 成功 |
| Hook 状态 | 内核日志出现实际 `dispatcher verified at slot`，或 fail-closed 明确停用重定向 | 仅「能开机」不代表 Hook 生效 |
| KernelSU Root | 兼容官方 KernelSU v3.3.0 的 Manager 可识别内核并经授权正常提权 | 需真实运行测试 |
| 稳定与权限 | 维持 Enforcing，至少经过一次完整重启和授权/撤销测试 | 不通过不能宣称稳定 |

内核日志中的两种关键分支：

- `dispatcher verified at slot N`：证明分发器槽位读回与写入值一致，但不代表所有 KernelSU Hook 或 Root 必定可用。
- `dispatcher patch failed; disabled syscall redirection`：说明 fail-closed 保护工作，启动可能恢复，但 Root 功能很可能缺失。

**当前 TEST2 的所有真机验收均为未完成。**
