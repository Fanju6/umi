# KernelSU for Xiaomi Mi 10 (umi)

基于 **[官方 KernelSU](https://github.com/tiann/KernelSU)** 的小米 10（`umi`）移植项目，适配 **LineageOS 23.2 / Android 16 / Linux 4.19**。提供固定上游版本、可审查的兼容补丁、自动构建与镜像完整性检查，以及真机验收记录。不使用 KernelSU Next。

## 支持范围

| 项目 | 当前测试条件 |
| --- | --- |
| 设备 | Xiaomi Mi 10（`umi`） |
| ROM | `LineageOS 23.2-20261004-NIGHTLY-umi` |
| 内核 | Linux 4.19.325，Clang 18 |
| KernelSU | 官方 `v3.3.1` 迁移分支；`v3.3.0 TEST2` 回滚基线 |
| 真机功能 | 启动、SELinux Enforcing、应用 Root、授权隔离、重启保持已通过；Manager 首次自动安装 ksud 由测试者确认 |
| 发布 | 尚未发布稳定版本，安全审计仍在进行 |

**分支说明：** 默认 `main` 保存已经真机验证的 **KernelSU v3.3.0 TEST2**。v3.3.1 代码在 [PR #3](https://github.com/Fanju6/umi/pull/3)，首次安装适配在其上的 [PR #4](https://github.com/Fanju6/umi/pull/4)。**不要将未合并的 v3.3.1 功能误认为已包含在 `main`。**

## 快速导航

- [当前版本与真实验收结果](docs/STATUS.md)
- [构建指南与 CI 使用](docs/BUILD.md)
- [源码架构与目录说明](docs/ARCHITECTURE.md)
- [全部文档索引](docs/README.md)
- [贡献指南](CONTRIBUTING.md)

## 设计与安全

使用固定 Git SHA 获取 LineageOS 内核和官方 KernelSU，通过 `scripts/patch_*.py` 施加仅针对 Linux 4.19 的兼容改动；不维护整体复制的内核树，也不修改官方 Manager 的用户空间代码。

仅对表中的 **指定设备和 ROM 构建** 保有真机证据。编译成功不代表镜像可刷；默认不自动刷机、不提供稳定 Release。Linux 4.19 SELinux 事务和 Manager/Seccomp 的部分静态安全门禁仍待正式审查。测试前应保留对应 ROM 的原始 Boot 和恢复方案。

早期曾出现已查明原因的 **v3.3.0 旧实验镜像启动失败**，后续 TEST2 与 v3.3.1 已成功启动。不要使用已知失败的旧镜像，原因及 SHA-256 见[历史故障档案](docs/history/README.md)。

本项目为社区移植，不代表 LineageOS 或 KernelSU 官方发布。
