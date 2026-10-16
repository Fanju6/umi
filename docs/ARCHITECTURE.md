# 工程架构

本仓库**不存储整体修改后的 Linux 内核源代码**，而是通过固定的官方 KernelSU 与 LineageOS 上游提交，将差异实现为可审查的兼容补丁。

```text
config/upstream.env                   固定上游分支和 Git SHA
scripts/prepare_sources.sh            克隆内核和 KernelSU，接入 Kbuild
scripts/apply_patches.py              按官方 SHA 和版本统一调度补丁
scripts/apply_compat.py               基础内核 API 兼容
scripts/patch_*.py                    Linux 4.19 兼容与安全修复
scripts/inspect_*.py                  源码/boot/Manager 静态分析
scripts/build_kernel.sh               Clang 18 / Kbuild 构建
scripts/check_build_output.py         Image / vmlinux / umi DTBO 验收
scripts/check_experimental_boot.py    镜像 Ramdisk / DTB / AVB 等验证
.github/workflows/                    CI 审计、编译与受控封装
tests/                                Python 补丁和安全回归
docs/                                 使用、维护、验收和历史记录
.work/                                本地构建产物，Git 忽略
```

## 构建数据流

```text
固定 Git SHA 的 LineageOS + 官方 KernelSU
                  ↓
           源码准备 / Kbuild 接线
                  ↓
      对旧内核应用带源码锚点的补丁
                  ↓
           单元测试 / 静态审计
                  ↓
         vmlinux + Image + DTB/DTBO
                  ↓
          原版 Boot 提取及核对
                  ↓
      仅替换 Kernel 并重算 AVB 哈希
                  ↓
            离线结构和哈希验收
                  ↓
       独立的真机功能与安全验收
```

## 兼容性关键点

- **ARM64 syscall Hook**：历史失败来自 4.19 PMD/PUD Block 映射识别与 dispatcher 失败后未 fail-closed，详见 [故障分析](BOOT_FAILURE_20261014.md)。
- **旧内核 API**：VFS、mount/fsnotify、umount、seccomp/task_work 与现代 KernelSU 不同。
- **SELinux**：旧 4.19 policydb/flex_array 使用原生事务路径，禁止结构体强转或关闭 Enforcing；异常/并发路径仍需独立审计。
- **Manager 首装**：官方 Manager 内置的 `libksud.so`、`/data/adb/ksud` 和 kernel FD 引导属于不同职责；功能已有用户真机确认，但后执行 FD Hook 的独立机制归因尚未完成。

## 分支关系

`main` 维护官方 KernelSU v3.3.1 与 Manager 首次部署适配；v3.3.0 TEST2 已退役为历史 Git 提交，不再通过主分支的旧工作流构建。改进时须保持上游版本固定、补丁可重复、失败即拒绝、测试证据有出处。
