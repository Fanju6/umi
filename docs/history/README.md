# 开发记录（历史归档）

这里的文字按**当时的调查时间**保留，可能写着“编译失败”“不能启动”“尚未验证”；这些不等于当前版本仍存在问题。最新结论见 [当前状态](../STATUS.md)。

- [2026 年 10 月逐轮开发日志](2026-10-development-log.md)：原 `docs/STATUS.md`。
- [2026-10-14 首次启动失败](../BOOT_FAILURE_20261014.md)：pstore 证明 `init ENOSYS`、ARM64 Hook 修复方案。
- [3.3.0 TEST2 真机验收](../UMI_TEST2_REAL_DEVICE.md) 与 [旧版 ksud 补救](../UMI_TEST2_ROOT_BOOTSTRAP.md)。
- [3.3.0 首次安装缺口](../KSUD_FIRST_INSTALL_GAP.md)。
- [3.3.1 迁移过程](../KERNELSU_V331_MIGRATION.md) 与 [Manager FD 原型](../EXPERIMENT_MANAGER_BOOTSTRAP_331.md)。

**历史已知无法启动的镜像 SHA-256：** `b5701bb8347ea4d37c584b96eedd00f6e51d867aa9a68ec21d75a16f85ae2aaf`，禁止使用。后续 TEST2 和 v3.3.1 已由真机证实正常启动。
