# 构建指南

本项目采用固定上游 SHA 的构建方式。默认 `main` 为官方 KernelSU v3.3.1；历史 v3.3.0 TEST2 保留在 Git 提交记录中。切换上游版本时，必须重新通过 CI 与真机验证，不得混用用户空间组件。

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

## 统一兼容补丁入口

以下命令是本仓库唯一推荐的补丁执行方式。入口从 `config/upstream.env` 核实官方 KernelSU 与 LineageOS 的固定 SHA，并检查实际检出的源码 HEAD。按版本执行完全一致的固定补丁顺序，失败即停止：

```bash
python3 scripts/apply_patches.py --plan
python3 scripts/apply_patches.py --profile v3.3.1
```

默认 `--profile auto` 使用配置中的锁定版本；`v3.3.0` 仅用于历史 TEST2 对照。现代 v3.3.1 共执行 16 项补丁，旧版 v3.3.0 维持 14 项；详细顺序由 `scripts/apply_patches.py` 定义并用回归测试固定。不要在工作流里另写一份补丁列表。

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
| `experimental-boot.yml`（历史） | v3.3.0 TEST2 旧版构建工作流已归档于 `docs/history/experimental-boot-v330.yml`，不再作为 `main` Actions 执行 |
| `stock-boot-audit.yml` | 对原版 Boot 的只读审计 |

Boot 封装仅使用与设备 ROM 完全对应且经过 SHA-256 校验的原版镜像，保留原 Ramdisk、DTB、Header 和 AVB 属性。CI **从不刷机**。兼容补丁现采用统一入口；v3.3.1 Boot 工作流可在 `main` 上手动触发，仍保留来源、镜像布局、AVB 和安全门禁验证，尚无稳定 Release。
