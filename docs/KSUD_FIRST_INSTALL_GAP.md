> **历史 v3.3.0 首装问题：** 这份文档保留 TEST2 当时的真实故障和人工补救方法。v3.3.1 Manager 无预装 ksud 的自动安装现已获测试者确认；详见 [真机验收](V331_REAL_DEVICE_ACCEPTANCE.md)。

# KernelSU 3.3.0 on umi: 首次自动部署 ksud 的真实缺口

状态：**TEST2 已成功启动、管理员正常、普通应用 su 授权/拒绝/恢复及跨重启有效**，但首次刷入仅替换 Kernel 时，需要使用 Rooted debugging 运行官方 `ksud install`。不能把此体验包装成完整开箱即用 Root。

## 为什么第一次缺 ksud？

1. TEST2 生成器 `.github/workflows/experimental-boot.yml` 用新内核替换 stock boot image 的 kernel 部分，专门要求 ramdisk SHA256 与原版完全一致。这样最大程度降低了首次真机调试的启动风险，但**完全没有配套 `ksud` 首次用户空间安装**。
2. 官方 KernelSU v3.3.0 `kernel/runtime/ksud.h` 固定 `KSUD_PATH="/data/adb/ksud"`，`kernel/feature/sucompat.c` 执行 `filp_open(KSUD_PATH,O_PATH,...)`；第一次 `ENOENT` 已被真机日志证实。
3. **官方 Manager 其实自带自动安装机制**：`manager/app/src/main/java/me/weishu/kernelsu/ui/MainActivity.kt` 在 `isManager && !requireNewKernel()` 时执行 `install()`；`KsuCli.kt` 使用 APK 自带 `libksud.so debug su` 先获取 Root，再执行 `ksud install`。
4. 初次安装在本设备未完成，进入 Root 获取失败状态。外部 ADB Root 安装官方 `ksud` 后，Manager 恢复正常、并很可能又从 APK 自动复制了一次 `libksud.so` 至 `/data/adb/ksud`，符合重启后尺寸/权限变化。
5. **关键待验证：Manager 首次通过 `libksud.so debug su` 获取内核超级调用 FD 为什么失败？** `userspace/ksud/src/ksucalls.rs` 会先扫描继承的 `[ksu_driver]` fd；不存在时使用 reboot-magic 获取 fd。官方 `kernel/supercall/supercall.c` 使用 `reboot` kprobe 提供该功能，而本仓库的 `scripts/inspect_manager_419.py` 已证明 4.19 的 `secure_computing` 在 `trace_sys_enter` 前，Seccomp 可能阻断 magic-reboot 的通道。因此是**强嫌疑路径，但没有首次 Manager 子进程的 ioctl/errno 跟踪证据，不能断言为唯一根因**。

## 真正的产品级验收标准

在 **无 `/data/adb/ksud` 的全新安装**中，用户只需刷入由项目构建的镜像、安装官方 Manager，并打开一次，应该成功部署用户空间程序、完成正常 Root 授权，**不要求启用 Rooted debugging、ADB Root、Recovery 改写 /data 或禁用 SELinux**。

要达成这个标准，应解决 Manager 初次授权 FD 获取路径或者设计审核通过、能在文件系统挂载后执行的受控首次部署机制。绝不能仅在编译时把 `ksud` 塞进早期 ramdisk、假设 `/data` 已解密挂载；对 umi 的 Android init 时序、文件访问控制、签名/哈希、后续系统 OTA、回滚都需独立审查。

## 当前可立即执行的过渡方案（不是产品级自动初始化修复）

新增 `scripts/umi-ksud-bootstrap.ps1`：

- 无参数：只读检查设备、ROM、Android 已启动、SELinux、Manager 和内核版本。
- `-Install`：显式请求用户已开启的 Rooted debugging → 验证真实 ADB UID=0 → 下载官方 v3.3.0 ksud → SHA256 和大小双校验 → 官方 `ksud install` → 验证 `ksu_file` SELinux 标签和散列；若文件已存在则保持不变。
- 从不自动刷分区、不修改系统属性或禁用 SELinux；独立 PowerShell，用户自行运行。它消除多步手动部署，**但并没有免除 Rooted debugging**。
- CI 源码测试对 pin/hash、环境门禁、免刷机和保守拒绝行为执行静态回归。

## 下一研发阶段

- 在当前正常 Root 的环境，用官方 `libksud.so debug su` 及 `adb logcat` 获取成功路径的用户态观测（**仅诊断，不卸载已有 ksud 来制造故障**）。
- 在单独分支构建可审查的首次初始化修复候选；对照已知良好 TEST2，增加隔离的真机启动/Root 测试。
- 不以「CI 成功」「自动启动服务」替代真实首次安装验收，原 TEST2 内核不动。
