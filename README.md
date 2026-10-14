# Xiaomi Mi 10 (umi) · LineageOS 23.2 × 官方 KernelSU

本仓库用于研究并移植 **[官方 KernelSU](https://github.com/tiann/KernelSU)** 至小米 10（`umi`）的 LineageOS 23.2 内核（Linux 4.19）。**不使用 KernelSU Next**。

> [!WARNING]
> **实验阶段。已通过官方 KernelSU 3.3.0 + umi Linux 4.19 的完整内核编译与链接，但尚未完成真机启动和功能验证；当前不提供可刷写的 boot.img。**
> 请勿在此基础上生成的未经验证镜像上直接覆盖手机原始 boot 分区。

## 上游

- [LineageOS SM8250 kernel · lineage-23.2](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/tree/lineage-23.2)
- [LineageOS umi device tree](https://github.com/LineageOS/android_device_xiaomi_umi/tree/lineage-23.2)
- [LineageOS sm8250-common](https://github.com/LineageOS/android_device_xiaomi_sm8250-common/tree/lineage-23.2)
- [tiann/KernelSU · v3.3.0](https://github.com/tiann/KernelSU/tree/v3.3.0)

## 已证实的移植阻塞

- 旧版 `selinux_state.ss` + `policy_rwlock` 与官方新版 `selinux_state.policy` + `policy_mutex` 不兼容。
- 旧版 `seccomp_filter` 不包含 `action_cache`；直接沿用新版缓存偏移属于内存破坏风险。
- 需检查 `MODULE_IMPORT_NS` 等较新内核宏、Kconfig/Kbuild 集成、Clang CFI、ARM64 调用约定以及启动时序。

## 实施原则

1. 固定上游版本并保留第三方代码来源，所有兼容修改以可审查的补丁/脚本保存。
2. 首先验证未修改的内核基线，再移植 Root 支持。
3. CI 静态审查和编译通过 **不代表** 可刷写；只有真机验证以后才允许发布刷机产物。
4. 不降级 SELinux 到 Permissive，不隐瞒运行时失败，不合并不安全的结构强转。

后续自动化、源代码改动和检查详见仓库中的 `docs/` 与 `scripts/`。

## 已完成的 CI 与实机只读预检

- [整核链接、Image、umi DTBO 完整验收](https://github.com/Fanju6/umi/actions/runs/38555215723)：成功，但仍是不可刷写的编译产物。
- [Windows PowerShell / Linux 真机只读预检](docs/DEVICE_PREFLIGHT.md)：仅获取版本、SELinux、槽位和分区名称，不写入设备。
- SELinux 策略运行时安全、Manager 授权和真机启动验证均未完成。
