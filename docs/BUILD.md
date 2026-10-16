# 构建指南

本项目采用固定上游 SHA 的构建方式；请先确定所在分支。默认 `main` 是 v3.3.0 TEST2，v3.3.1 迁移见 PR #3 / PR #4。本指南的 v3.3.1 补丁命令仅适用于包含它们的开发分支。

## 环境

CI 使用 Ubuntu 24.04、Clang/LLD/LLVM 18、aarch64/arm GNU 交叉工具链与 Python 3：

```bash
sudo apt-get update
sudo apt-get install -y clang-18 lld-18 llvm-18 gcc-aarch64-linux-gnu gcc-arm-linux-gnueabi bc bison flex libssl-dev libelf-dev
```

Clang 18 已用于已测试镜像的编译，但与官方 ROM 原版 Clang 21 并非相同工具链；更换工具链须单独验证。

## 拉取源码

```bash
bash scripts/prepare_sources.sh
```

该脚本读取 `config/upstream.env`，将固定 SHA 的 LineageOS 内核和官方 KernelSU 拉取到忽略 Git 的 `.work/` 目录、接入 Kbuild/Kconfig。**不要通过浮动的上游 main 替代锁定版本。**

## Linux 4.19 补丁顺序（v3.3.1 首装分支）

```bash
python3 scripts/apply_compat.py .work/KernelSU
python3 scripts/patch_vfs_419.py .work/KernelSU
python3 scripts/patch_legacy_apis.py .work/KernelSU
python3 scripts/patch_policy_419.py .work/KernelSU
python3 scripts/patch_task_work_331.py .work/KernelSU
python3 scripts/patch_manager_postexec_fd_419.py .work/KernelSU
python3 scripts/patch_sulog_419.py .work/KernelSU
python3 scripts/patch_dispatch_419.py .work/KernelSU
python3 scripts/patch_syscall_failclosed_419.py .work/KernelSU
python3 scripts/patch_arm64_block_walk_419.py .work/KernelSU
python3 scripts/patch_avtab_419.py .work/KernelSU
python3 scripts/patch_filename_419.py .work/KernelSU
python3 scripts/patch_type_419.py .work/KernelSU
python3 scripts/patch_selinux_core_419.py .work/kernel
python3 scripts/patch_rules_419.py .work/KernelSU
python3 scripts/patch_umount_419.py .work/kernel .work/KernelSU
```

所有补丁都以固定源码为前提。若脚本发现上游锚点变化而失败，**不要跳过错误或强行继续编译**。

## 验证与构建

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_umi_preflight.py config/umi_preflight_20261014.json
python3 scripts/audit.py .work/kernel .work/KernelSU --expect-blocked selinux-abi manager-handshake
bash scripts/build_kernel.sh ksu
```

编译完成后检查 `.work/output-ksu/arch/arm64/boot/Image`、`vmlinux`、DTB/DTBO 与 `.work/build-manifest-ksu.json`；**此过程不产生完整 boot.img**。

## GitHub Actions

| 工作流 | 用途 |
| --- | --- |
| `source-audit.yml` | 单元测试与上游安全审计（保留当前预期 BLOCK） |
| `kernel-smoke.yml` | 快速驱动目录诊断 |
| `kernel-compile.yml` | Image、vmlinux、DTBO 整核构建 |
| `experimental-v331-boot.yml` | v3.3.1 隔离 Boot 封装与结构验证 |
| `experimental-boot.yml` | v3.3.0 TEST2 专用，不与 v3.3.1 混用 |
| `stock-boot-audit.yml` | 对原版 Boot 的只读审计 |

Boot 封装仅使用与设备 ROM 完全对应且经过 SHA-256 校验的原版镜像，保留原 Ramdisk、DTB、Header 和 AVB 属性。CI **从不刷机**。目前工作流仍存在补丁步骤重复、文档哨兵触发等历史设计；工作流优化将单独评估与实施，避免改变已经在设备上验证的产物。
