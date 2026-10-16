# 当前开发与验收状态

**更新：2026-10-16。** 原先的逐日故障排查已移至 [历史开发日志](history/2026-10-development-log.md)，本页仅记录当前结论。

## 上游与分支

- **设备**：Xiaomi Mi 10（umi），LineageOS `23.2-20261004-NIGHTLY-umi`，Android 16。
- **内核**：LineageOS `71b13e62f057a649b77fe4062feb73ee72ad609c`，Linux 4.19.325。
- **官方 KernelSU v3.3.1**：`0c0fdb960178fa12d80d6cbcfdcb6ad8be6a865d`。
- **默认 main**：仍是 KernelSU v3.3.0 TEST2；升级在 [PR #3](https://github.com/Fanju6/umi/pull/3)，首次 Manager 引导在 [PR #4](https://github.com/Fanju6/umi/pull/4)，两者仍为 Draft。

## v3.3.1 真机证据

| 检验项 | 当前状态 |
| --- | --- |
| vmlinux / Image / umi DTBO | [PR #3](https://github.com/Fanju6/umi/actions/runs/38701939945) 与 [PR #4](https://github.com/Fanju6/umi/actions/runs/38702463550) 完整编译、链接成功 |
| v3.3.1 实验 Boot | [独立镜像构建](https://github.com/Fanju6/umi/actions/runs/38703137664) 成功，17 项结构检查与 SHA-256 通过 |
| Android 16 启动 | ADB 实测 `sys.boot_completed=1`、ROM 与内核版本吻合 |
| SELinux | ADB/终端实测持续 `Enforcing` |
| Root 与权限域 | 应用终端实测 `uid=0(root)` / `u:r:ksu:s0` |
| ksud 版本 | 安装后 `/data/adb/ksud` 与 v3.3.1 Manager 内置 `libksud.so` **SHA-256 相同** |
| 授权撤销/恢复、重启保持 | 测试者明确报告通过，后续缺少完整原始日志 |
| 无预装 ksud 时 Manager 自举 | **测试者明确确认通过**：先无文件，未用 adb root/手动安装；缺少 FD Hook 独立归因日志 |
| 模块与 SELinux 策略、长期稳定性 | 测试者反馈正常；具体参数、模块清单和持续时间未附 |

完整的实际输出、测试者反馈及证据级别见 [真机验收记录](V331_REAL_DEVICE_ACCEPTANCE.md)。

## 发布边界

**基础功能在指定设备上已验证，不等于完成安全审计或适用于其他版本 ROM。** `selinux-abi` 和 `manager-handshake` 的静态安全门禁尚未签收；这与真机功能通过可以同时成立。没有稳定 Release；工作流中的实验镜像 `safe_to_flash=false` 标记也不应因一次真机测试而自动修改。

历史首版因 ARM64 syscall Hook 失败导致的 `init ENOSYS` 已定位并修复，但该失败镜像仍禁止刷入，见 [历史记录](BOOT_FAILURE_20261014.md)。
