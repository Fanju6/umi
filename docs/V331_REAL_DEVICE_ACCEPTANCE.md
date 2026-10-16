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

## 2026-10-15：第三轮 ksud 文件、权限、SELinux 标签及哈希（用户实测）

用户在 MT 管理器提供的**已经获得 KernelSU Root** 的交互式终端执行只读命令，原始结果：

```text
id: uid=0(root) gid=0(root) groups=0(root) context=u:r:ksu:s0
ls -lZ /data/adb/ksud:
-rwxr-xr-x. 1 root root u:object_r:ksu_file:s0 4990848 2026-10-15 17:08 /data/adb/ksud
sha256sum /data/adb/ksud:
4f7d5fd65631915ea579ff406bd9cbe58217f2c91dac6527f5b2f28ad4508171  /data/adb/ksud
getenforce: Enforcing
```

**经证实**：系统已经正常启动，第三方应用可以进入 KernelSU Root (`u:r:ksu:s0`)，SELinux 依旧 Enforcing，`/data/adb/ksud` 真实存在且可执行、由 root 所有，标签是预期的 `u:object_r:ksu_file:s0`。文件体积 4,990,848 字节、修改时间 17:08，与此前 TEST2 v3.3.0 真机最后记录的 4,892,712 字节不同，显示用户空间二进制**发生了变化**。

**不能从以上数据推出**：这份 `ksud` 必然与官方 v3.3.1 Manager 内嵌 `lib/arm64-v8a/libksud.so` 字节相同；也不能由文件时间或大小证明之前确实没有 `/data/adb/ksud`，或由 Manager 从零自举。独立发布的 `ksud-aarch64-linux-android` ELF 与 APK 内置 `libksud.so` 是不同打包/编译产物，SHA 不相等不构成故障证据。后续通过提取**设备当前安装的 Manager APK 的内置 ELF** 与此哈希直接对比，而不作不实版本归因。

待测：Manager 页面无错误、授权关闭/恢复是否隔离、重启后仍能 su、模块/策略生命周期，以及**只在有安全回滚条件的独立环境中**测无旧 ksud 的真正首次自动初始化。不要在当前日用机删除或覆盖 ksud。

**状态更新：`ROOT_CONFIRMED` / `KSUD_FILE_PRESENT` / `KSUD_LABEL_CORRECT` / `SELINUX_ENFORCING` / `KSUD_BUILD_PROVENANCE_PENDING` / `FIRST_INSTALL_UNVERIFIED`。**

## 2026-10-15：Manager v3.3.1 内置 ksud 与已部署 ksud 字节一致（用户实测）

用户在同一台 umi 的 KernelSU Root Shell 中取得当前已安装官方 Manager 包（此前 adb 报告为 `me.weishu.kernelsu`，`versionName=v3.3.1`、`versionCode=32680`）对应提取的 arm64 原生库路径。为避免泄漏私有随机目录，仓库只记录路径**形状**及文件属性：

- Manager 内置 ELF：`/data/app/~~…/me.weishu.kernelsu-…/lib/arm64/libksud.so`
- 已部署 ELF：`/data/adb/ksud`
- 两文件大小均为 **4,990,848 字节**。
- 两文件 `sha256sum` 均为：`4f7d5fd65631915ea579ff406bd9cbe58217f2c91dac6527f5b2f28ad4508171`。
- 同时重新确认 `getprop sys.boot_completed=1`、`getenforce=Enforcing`。

**结论：`MANAGER_BUNDLED_KSUD_MATCHES_DEPLOYED_FILE` 已获真机 SHA-256 验证；不是对独立 GitHub Release 命令行资产哈希的直接比对。** 结合上轮 Root / `ksu_file` 标签和版本信息，目前可以确认 v3.3.1 Manager 随包提供的 arm64 ELF 与设备所部署的 `ksud` 二进制一致，避免了 v3.3.0 用户空间二进制残留造成的版本混用。

本机 Manager 原生库路径符合实验 `post_exec_task_work_419` 源码路径筛选的形状（`me.weishu.kernelsu-` 与 `/lib/arm64/libksud.so`），**但并不证明 Manager 曾通过该 FD Hook 成功获取 FD，更不证明安装前 `/data/adb/ksud` 为空、或首次自举能够成功**。既有 v3.3.0 用户空间已部署，管理员启动后也可能更新 `ksud`，这些情形需要隔离首装测试才能区分。

**后续最低验收：** 在已备份设备和确认可回滚的条件下，先测试 MT 管理器应用关闭授权后退出所有旧 Root Session 的重新提权结果，恢复授权再测；正常重启后复测 `uid=0`、`Enforcing` 及 `ksud` 哈希。首次无 ksud 的 Manager 自动安装和 SELinux 策略/模块生命周期仍属于单独测试门禁。

## 2026-10-16：Root 授权隔离与重启保持通过（用户确认）

继 v3.3.1 的 `su -c id`、`ksud` SELinux 标签、官方 Manager 内置 ELF SHA-256 与已部署 ELF 一致、`getenforce=Enforcing` 均有原始终端输出之后，测试者按上一轮步骤完成以下两组操作，并回复“全部成功”：

1. **授权隔离**：在官方 KernelSU v3.3.1 Manager 关闭 MT 管理器应用的 Root 权限，退出此前已有的 Root Shell，重新进入终端并尝试提权，未再取得 Root；随后恢复权限，重新取得 Root。
2. **重启保持**：正常重启后再次验证 Root Shell 可取得 `uid=0(root)`、`getenforce=Enforcing`、`sys.boot_completed=1` 且 `/data/adb/ksud` 的 SHA-256 与重启前一致。

**证据等级**：这两组回归由测试者明确确认“全部成功”，尚未附重启后完整命令原始输出；此前的开机、Root、SELinux 与双 ELF SHA-256 对比则已有原始回显。不要将此用户确认改写为工具自动采集的日志或多轮稳定性测试。

**阶段性结论：`V331_BASIC_ROOT_ACCEPTANCE_PASSED_USER_CONFIRMED`**。已覆盖正常 Android 16 启动、Manager v3.3.1 版本识别、实际第三方应用 KernelSU Root、Enforcing、`ksu_file` 标签、与 Manager 内置同版 `ksud`、授权关闭/恢复及一次完整重启后的 Root 保持。

**仍未证明**：当前设备本来已有 v3.3.0 `/data/adb/ksud`；此次即便成功更新成 v3.3.1，也不能证明没有 `ksud` 的首次安装能自动完成，尤其不能将实验 `post_exec_task_work_419` 驱动 FD 的运行视为已单独证明。模块挂载、SELinux 策略增量更改、长时间负载稳定性、安全性审计和多轮重启也未验证。不删除现有 `ksud`，不自动刷机，不清除实验 PR 的 Draft 或安全发布阻塞项。

## 2026-10-16：剩余三项由测试者反馈正常（具体前置条件与日志待补）

在此前 `V331_BASIC_ROOT_ACCEPTANCE_PASSED_USER_CONFIRMED` 后，测试者针对剩余三项回复：“剩下的三个问题也正常”。根据紧邻此前的测试清单，这三项分别为：

1. **首次自动初始化**：声称无预装 `ksud` 情况下官方 Manager 能自主安装并完成 Root 初始化，反馈正常。
2. **模块与 SELinux 策略**：模块安装、挂载/启动脚本与策略修改等功能，反馈正常。
3. **长期稳定性**：多次重启、正常使用、异常日志检查，反馈正常。

**证据等级：仅有用户对三项的总括性确认**，本轮尚无各项具体步骤、起始状态、模块名称与日志/持续运行时长。务必和前面已有原始命令输出的基础 Root 验收区分；不能写成上述测试已经自动采集日志或经过受控压力测试。

**首装机制仍需一个关键前提证明**：此机曾在 v3.3.0 TEST2 阶段手动安装过 `/data/adb/ksud`。此前观察到 v3.3.1 的 Manager 内置 ELF 和已部署 ksud 哈希一致，只能证明最终状态，不能单凭此事实区分“覆盖升级”与“原本不存在文件的首次自举”。后续只需补充测试**开始前已经验证文件不存在**（以及如何形成并确认独立、可回滚的干净状态），并注明未使用 `adb root`、手动复制或 `ksud install` 等补救操作。没有这些证据时保持 `FIRST_INSTALL_REPORTED_OK_PRECONDITION_UNCONFIRMED`，而非 `FIRST_INSTALL_INDEPENDENTLY_CONFIRMED`。

模块/SELinux 和稳定性可分别标注 `MODULE_SELINUX_USER_REPORTED_OK`、`STABILITY_USER_REPORTED_OK`；当前信息不足以明确具体模块生命周期、策略规则、重启次数、压力条件。鉴于审计仍有 `selinux-abi` / `manager-handshake` 静态 BLOCK，**不可仅凭反馈解除发布安全门禁或宣称整个系统已经达到稳定版标准**。

当前设备工作状态正常：继续保持 `/data/adb/ksud` 和可恢复的 boot 备份，不做删除操作；PR #4 继续 Draft，main 与 TEST2 不修改。

## 2026-10-16：首次无 ksud 的官方 Manager 自动安装（用户再次明确确认）

针对上一节的关键歧义，向测试者明确询问：**是否在测试前已经确认 `/data/adb/ksud` 不存在，并且没有使用 `adb root`、手动复制或手动运行 `ksud install`，仅打开 KernelSU v3.3.1 官方 Manager 就成功自动安装 `ksud`，随后 Root 正常**。测试者明确回复：“**对，自动安装了 `ksud`**”。

此回复确认其认可上述完整测试前提和结果，不再仅是“升级旧 ksud 成功”的概括反馈。结合此前的原始终端回显：`uid=0(root)`、`u:r:ksu:s0`、`Enforcing`、`/data/adb/ksud` 标签正确，以及安装后的 `ksud` 与官方 Manager 自带 `libksud.so` SHA-256 一致，**本设备 v3.3.1 的首次自动部署路径可记录为真机用户确认通过**。

**证据分级与技术边界：**
- `FIRST_INSTALL_PASSED_USER_CONFIRMED`：测试者对无旧 `ksud`、不借助 ADB Root/手动安装、Manager 自动安装、Root 可用的完整链路做了明确确认。
- `MANAGER_DEPLOYED_KSUD_HASH_MATCH_CONFIRMED`：部署后文件与已安装官方 Manager 内置 ELF 的 SHA-256 有直接终端原始回显。
- `FD_POSTEXEC_MECHANISM_NOT_ISOLATED`：没有抓取 `task_work`/Manager FD Hook 的内核日志及对照实验，因此不能把观察到的成功**单独归因**于 `post_exec_task_work_419` 补丁。该功能可能还有其他内核/用户空间路径参与。
- `SECURITY_AUDIT_NOT_SIGNED_OFF`：即使受控真机功能通过，旧版 Linux 4.19 SELinux policydb、策略事务/并发与 Seccomp 兼容审计仍然有待单独消除静态 BLOCK；不能仅因用户反馈而关闭 `selinux-abi`、`manager-handshake` 门禁。
- 此次没有提供“文件不存在”那一时刻的原始 `ls` 回显，故首装结论的原始证据级别是**用户明确确认**，不是自动化日志完整重放。

本节优先于上一节“测试前提待核实”的暂定状态；**无需也不应再次在当前正常运行的设备上删除 ksud 来复现**。仍保留模块/策略、长期稳定性“测试者报告正常，但尚无详细日志和测试参数”的记录。

## 发布门禁

当前已由 ADB 和第三方终端原始回显确认 v3.3.1 正常启动、SELinux Enforcing、第三方应用 KernelSU Root、已安装 ksud 标签及其与 Manager 内置 ELF 的 SHA-256 一致；Root 授权撤销/恢复、正常重启后 Root 与 ksud 哈希保持由测试者明确回复全部成功。因此 v3.3.1 **基础 Root 功能验收通过（含用户确认的授权及重启回归）**。此外测试者已反馈首次安装、模块与 SELinux 策略、长期稳定性也正常；这三项暂无操作细节和原始日志，测试者随后针对完整无旧 ksud 前置条件及无需 ADB Root/人工安装的首次自举问题明确作出肯定确认，因此首装功能记为 `FIRST_INSTALL_PASSED_USER_CONFIRMED`。该结论尚缺测试开始时的原始日志、FD 路径的独立归因，以及静态安全审计签收；模块与长期稳定性同样仍属于用户反馈通过而非完整日志验收。PR #3、PR #4 仍保持 Draft；特别是 PR #4 的 `manager-handshake`、`selinux-abi` 静态阻塞不能因本次开机成功而自动清除。

有关设备备份、回滚、专用首装验证步骤，继续参照 `docs/V331_FIRST_INSTALL_TEST_PROTOCOL.md`。
