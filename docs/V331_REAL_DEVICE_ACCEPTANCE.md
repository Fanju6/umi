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

## 发布门禁

当前基础阶段只通过**用户口述的正常开机、版本显示**，其余仍需逐项实际验证。PR #3、PR #4 仍保持 Draft；特别是 PR #4 的 `manager-handshake`、`selinux-abi` 静态阻塞不能因本次开机成功而自动清除。

有关设备备份、回滚、专用首装验证步骤，继续参照 `docs/V331_FIRST_INSTALL_TEST_PROTOCOL.md`。
