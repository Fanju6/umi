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

## 2026-10-15：TEST2 真机启动成功（用户 ADB 实测）

用户在 Xiaomi Mi 10 umi 上刷入 TEST2 后，已能正常进入 Android，并从 adb 获得以下结果（仅记录必要事实，不包含设备 ID 或其他个人标识）：

```text
adb shell getprop sys.boot_completed
1
adb shell uname -r
4.19.325-cip131-st15-perf-g71b13e62f057-dirty
adb shell getenforce
Enforcing
```

**阶段结论：Android 正常启动通过。** `-dirty` 与我们的自编译内核特征一致；但仅根据内核发行名并不能唯一证明已加载哪个字节级 boot.img，如有必要可另行核对编译器/打包散列。此结果与旧版因系统调用分发器导致的第一阶段 `init` 失败形成清晰对照。

TEST2 构建：GitHub Actions `#38678653507`，结果为 `success`，artifact `UMI-TEST2-HOOKFIX-UNVERIFIED-KernelSU3.3.0-boot`，源提交 `992dfbc1cbbb01e0b7b1bfbea82fedd6fecf362c`。成功不等于 Root 成功。

**剩余必测项目：**

- 官方 KernelSU v3.3.0 Manager 是否识别到 KernelSU 内核（需用户明确提供界面状态）。
- 对授权终端/ADB shell 运行 `id` 的实际结果，确认是否出现 `uid=0(root)`；不以 `su` 文件存在为通过条件。
- 查看登录后的 Hook 状态（`dispatcher verified at slot` 或 `dispatcher patch failed; disabled syscall redirection`），必要时结合 Android Kernel log / Recovery pstore 判定。
- 允许/拒绝授权流程、再次正常启动与 SELinux 保持 Enforcing 的情况。
- 内核内存补丁、SELinux 4.19 策略事务及 Manager/Seccomp 尚未完成真机稳定性验证，不将该构建标记稳定或发布正式 Release。

**状态：BOOT_SUCCESS / ROOT_NOT_YET_VERIFIED / SELINUX_ENFORCING / STABILITY_NOT_YET_VERIFIED。**

## 2026-10-15：Root 授权阶段的真实失败与已发现原因

测试结果：官方 Manager v3.3.0 显示「工作中 / 32601-2」，但提示「获取 root 失败」；`adb shell su -c id` 报 `su: inaccessible or not found`。内核日志记录了 `Crowning manager`、`ksu fd installed`，并在 sucompat Hook 中多次记录 `open ksud err: -2`。

官方 KernelSU v3.3.0 的 `KSUD_PATH` 为 `/data/adb/ksud`。此前 TEST2 构建仅替换内核而保留官方原版 Ramdisk，未安装匹配的用户空间 `ksud`。优先补齐用户空间程序并确认 SELinux 标签，**不要在尚未测试前认定必须继续重编内核**。

只读确认、用户自主条件安装及后续验证见 [TEST2 Root Bootstrap](UMI_TEST2_ROOT_BOOTSTRAP.md)。状态：BOOT_SUCCESS / MANAGER_RECOGNIZED / ROOT_FAILED / KSUD_MISSING_OR_INACCESSIBLE。

## 2026-10-15 14:25：官方 ksud 部署成功，Manager 恢复正常

用户确认：在开发者选项启用 **Rooted debugging** 后，\`adb root\` 成功，\`adb shell id\` 返回 \`uid=0(root)\`、\`context=u:r:su:s0\`；下载官方 KernelSU v3.3.0 的 \`ksud-aarch64-linux-android\`、SHA-256 校验通过后，在 ADB Root 下执行 \`/data/local/tmp/ksud install\` 成功，持久路径 \`/data/adb/ksud\` 已存在，权限 \`-rwx------ root:root\`，SELinux 标签为 \`u:object_r:ksu_file:s0\`。用户反馈 **KernelSU 管理器已经正常**。

**修正历史状态**：之前的「\`ksud\` 缺失」诊断得到可操作的验证和修复；既有的 \`adb shell su\` 找不到命令并不能证明 KernelSU Hook 永久失效，TEST2 的本次错误属于未部署 \`ksud\` 的用户空间初始化缺口。ADB Root 的成功与 APP 侧 Root 不是同一种验收。

真机状态更新为：
- BOOT_SUCCESS
- SELINUX_ENFORCING (之前证实；安装后待复查)
- KERNELSU_MANAGER_RECOGNIZED
- KSUD_INSTALLED_WITH_EXPECTED_SELINUX_LABEL
- MANAGER_REPORTED_NORMAL
- APP_ROOT_AUTHORIZATION_PENDING
- REBOOT_STABILITY_PENDING

详细验收路径见 [TEST2 Root Bootstrap](UMI_TEST2_ROOT_BOOTSTRAP.md)。在普通应用成功获取 Root、Enforcing 下拒绝授权有效且重启验证以前，仍归类 TEST2，不能宣称稳定发布。
