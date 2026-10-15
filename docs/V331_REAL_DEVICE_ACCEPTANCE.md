# umi / KernelSU v3.3.1 真机验收记录

本文件只记录用户明确确认的事实；不把源码 CI、正常开机或版本显示等同于 Root、Manager 首装和稳定性全面通过。

## 2026-10-15：首次启动状态（用户反馈）

目标：Xiaomi Mi 10 (umi)，LineageOS 23.2-20261004-NIGHTLY-umi，Android 16，官方 KernelSU v3.3.1 升级实验。

用户反馈：
- 已刷入本轮 KernelSU v3.3.1 构建的内核镜像；
- Android 正常开机；
- 设备显示 KernelSU 版本号与 v3.3.1 对应。

**当前结论：`BOOT_SUCCESS_USER_REPORTED` / `KSU_V331_VERSION_REPORTED`。**

注意：此次反馈暂未附本次设备上的 `sys.boot_completed`、`getenforce`、`uname`、可识别的镜像字节级哈希或 Manager 状态截图；因此不额外声称其已独立复核。此前 TEST2 v3.3.0 的更多功能验收结论不能直接转移到 v3.3.1。

## 下一轮应优先收集

1. Android 与内核：`adb shell getprop sys.boot_completed` 应为 `1`；`adb shell getenforce` 应为 `Enforcing`；`adb shell uname -r` 和 `adb shell getprop ro.lineage.version` 应与当前项目目标匹配。
2. 官方 v3.3.1 Manager：确认“工作中”，无“获取 Root 失败”红色警告、无安装失败；记录 UAPI/内核与 Manager 版本。
3. 普通终端应用（**不使用 adb root**）：先在 KernelSU Manager 授予 Termux Root，再由 Termux 执行 `/system/bin/su -c id`，应有 `uid=0(root)`。检查 `/data/adb/ksud` 是否存在、SELinux 标签是否为 `u:object_r:ksu_file:s0`。
4. 对该应用关闭授权后退出原有 Root Shell 并重试，应无法获得 `uid=0`；重新授权应恢复提权。
5. 正常重启后，再次确认 Android 启动完成、SELinux 仍为 Enforcing、Manager 工作中及 Termux Root 仍可用。
6. **首装关键断言仍未验证**：当前设备以前运行过 v3.3.0，并通过 ADB Root 安装过 `/data/adb/ksud`；如果本次只刷了 boot 而未清理 data，则本次启动及自动更新 `ksud` 均**不能证明**“原先没有 `/data/adb/ksud` 时官方 Manager 可以自举”。严格的无预装 ksud 首装测试应仅在专用可恢复设备或可靠备份隔离环境下进行，禁止在当前正常使用的设备直接删除 ksud。
7. 基础验证完成后再进行模块生命周期、SELinux 策略事务、长期稳定性和日志安全审计。

## 2026-10-15：第一轮 ADB 只读报告（用户提供原始输出）

此轮通过未授权 Root 的 ADB Shell 收集；不同于此前仅口述，本次有具体命令输出。为避免传播个人信息，仓库只保留软件版本与测试结论，不记录设备序列号、随机 APK 安装路径或完整私有日志。

| 检查 | 观测值 | 判定 |
| --- | --- | --- |
| 设备 / Android | umi / Mi 10 / Android 16 / API 36 | 通过 |
| ROM | LineageOS 23.2-20261004-NIGHTLY-umi / BP4A.251205.006 | 通过 |
| Android 启动 | sys.boot_completed=1；bootanim=stopped；已运行约 10 分钟 | 通过 |
| 内核编译标识 | Linux 4.19.325-cip131-st15-perf-g71b13e62f057-dirty；Clang 18.1.3 / LLD 18.1.3；2026-10-15 08:07:49 UTC | 与实验内核源码和 CI 编译时间相容，但不足以字节级证明 boot.img 相同 |
| SELinux | getenforce=Enforcing；ADB shell 为 u:r:shell:s0 | 通过 |
| Verified Boot | orange | Bootloader 未锁定的预期状态，不是安全验证通过的证明 |
| 官方 Manager APK | me.weishu.kernelsu / versionName=v3.3.1 / versionCode=32680 | 已安装版本确认；未验证「工作中」/授权 UI |
| KernelSU 内核痕迹 | logcat kernel 中有 hook_manager: unmark ... exec /apex/com.android.art/bin/artd | 有驱动 Hook 相关运行记录，但不能证明 Manager FD 和 su 成功 |
| ADB shell | uid=2000(shell)，command -v su 不存在 | 不可据此推断普通 Android APP Root 故障 |
| 受保护 ksud 文件 | 无法从 ADB shell 读取 | 未验证，不得断言不存在 |
| 内核 AVC 日志 | 该命令过滤窗口内无命中 | 不是全局无 AVC 的证明 |
| 首装无 ksud | 设备以前手动安装过 v3.3.0 ksud，未进行隔离干净 data 测试 | 未验证 |

**新状态：`BOOT_COMPLETE_CONFIRMED` / `SELINUX_ENFORCING_CONFIRMED` / `OFFICIAL_MANAGER_V331_APK_INSTALLED` / `APP_SU_PENDING` / `KSUD_FILE_PENDING` / `FIRST_INSTALL_PENDING`。**

下一步必须通过已授权的普通终端应用（如 Termux），而不是缺少 su 的 ADB Shell，实际执行 `su -c id`，并由授权 Root 检查 `ls -lZ /data/adb/ksud`、`sha256sum /data/adb/ksud`。之后再做授权撤销/恢复及重启回归。不能在原设备删除 ksud 或调用 adb root 来冒充首装成功。

## 2026-10-15：第三方应用终端 KernelSU 提权成功（用户原始回显）

用户在 MT 管理器（终端 Bash 位于 `/data/user/0/bin.mt.plus/files/term/bin/bash`）的交互式终端中执行 `su -c id`，实际输出：

```text
uid=0(root) gid=0(root) groups=0(root) context=u:r:ksu:s0
```

同时执行 `getenforce` 输出：

```text
Enforcing
```

**结论：`KSU_SU_ROOT_CONFIRMED`，`KSU_SELINUX_DOMAIN_CONFIRMED`，`ENFORCING_STILL_CONFIRMED`。** 这次输出证明实际进入了 KernelSU 的 Root 安全上下文；但此前 ADB shell 无 su 不构成失败，本轮也尚未验证关闭授权后拒绝提权。

执行 `su -c 'ls -lZ /data/adb/ksud; sha256sum /data/adb/ksud'` 时，MT 管理器 Bash 报错，将整个带分号的命令字符串呈现在 `No such file or directory` 的“命令名”位置。这一输出无法用作 ksud 缺失证据。由于用户提示符已是 `#`，下一步应**直接在现有 Root Shell 分别执行** `ls -lZ /data/adb/ksud` 和 `sha256sum /data/adb/ksud`，无需嵌套 `su -c`。

仍待验证：`/data/adb/ksud` 当前状态和哈希、Manager 首次自动安装、撤销与恢复 Root 授权、重启后 Root 可用性、模块与长期稳定性。**保留旧 ksud，不在日用设备删除或覆盖。**

## 发布门禁

当前已由用户的只读 ADB 原始输出验证正常完成 Android 启动、SELinux Enforcing 及官方 Manager APK v3.3.1 安装版本，且已确认第三方应用终端的 KernelSU Root 上下文与 Enforcing；ksud 文件、授权撤销以及首次初始化仍需单独真机验证。PR #3、PR #4 仍保持 Draft；特别是 PR #4 的 `manager-handshake`、`selinux-abi` 静态阻塞不能因本次开机成功而自动清除。

有关设备备份、回滚、专用首装验证步骤，继续参照 `docs/V331_FIRST_INSTALL_TEST_PROTOCOL.md`。
