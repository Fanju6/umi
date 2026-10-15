# 2026-10-14 · umi 实验 KernelSU boot.img 启动失败

## 已确认

- 机型：Xiaomi Mi 10 `umi`，Android 16 / LineageOS `23.2-20261004-NIGHTLY-umi`，非 A/B 布局。
- 官方 KernelSU 3.3.0 实验镜像：CI #38567509103 生成；SHA256 `b5701bb8347ea4d37c584b96eedd00f6e51d867aa9a68ec21d75a16f85ae2aaf`。
- 实验镜像静态检查（Boot Header v2、原 Ramdisk/DTB、AVB Hash Footer）全通过，但**真机无法启动**。
- 使用官方原版 `boot.img` 恢复成功。实验版正式标记为 `KNOWN_BOOT_FAILURE`，不得作为已可刷版本推广。

## 目前未证实

尚不清楚失败发生在 Bootloader、内核初始化、第一阶段 init、SELinux policy 初始化/重载、或第二阶段 init / Zygote。此前采用 Clang18 的试验工具链，且没有完成**同一工具链构建的干净非 KSU 内核**的启动基线测试，因此不能简单归因于 KernelSU。

## 下一轮调查（严禁直接重复刷原文件）

1. 利用已恢复开机的原版系统只读检查 `/sys/fs/pstore` 是否还有上一次失败的 `console-ramoops` 或 `dmesg-ramoops`；部分设备权限受限或重启后覆盖，缺失不等于没有内核 panic。
2. 只读获取 `ro.boot.bootreason`、`sys.boot.reason`、`/proc/version`，根据是否有上一轮 kernel pstore 来确定启动阶段。
3. 离线对照官方原版 boot.img 内嵌 IKCONFIG 与 CI 构建 `.config`；需要区分 Clang/LTO/CFI/设备配置问题与内核源码改动。
4. 若仍无法定位，再构建不含 KernelSU 的同工具链基线以比较（不得把未经测试的基线镜像宣传成安全版）。
5. 单独审查早期 KSU init hook、4.19 的 SELinux policydb 更新与 Android 16 第二阶段 init 顺序，补上失败回滚和保守禁用条件。

**即使后来 CI 再次绿色，也不能覆盖真实失败事实。** 除非有真机启动成功且功能正常的证据，所有实验镜像均为不可证实安全的调试产物。

## 只读内核版本比对的新增发现

从官方 SHA256 锁定的 `boot.img` 的 Image 中成功提取了 5312 项 IKCONFIG 条目（CI #38574558265）。真实原版内核由 **Android Clang 21.0.0** 编译，基于 LLVM `r563880c`（构建信息还包含内部版本号 `14054515`）；此前的实验构建却使用了 **Ubuntu Clang 18.1.3**。原版 `CONFIG_LTO_CLANG=y`、`CONFIG_CFI_CLANG=y`、`CONFIG_CFI_PERMISSIVE=n`，也未启用 `CONFIG_KPROBES`，实验 KSU 构建启用了后者。

这不是启动失败的充分原因，但表明我们还没有建立严格的可比基线。已新增 `scripts/inspect_stock_kernel.py`，快速驱动编译 CI 将获取正常启动原版 Image 的原始 IKCONFIG 与本仓库编译出的完整 `.config` 进行逐项对比。**在修正 Clang、配置与确认失败阶段以前，不再生成给用户刷写的“修复版”。**

## 2026-10-15：pstore 证实 KernelSU 启动失败直接机制

收到 Recovery 导出的 `console-ramoops-0`（140806 字节）。**原始日志包含设备标识，绝不推送至 GitHub。** 精确观察：

- [0.000000] 运行的不是官方内核，而是 Ubuntu Clang 18.1.3 构建的 `4.19.325-cip131-st15-perf-g71b13e62f057-dirty`。
- [1.119505] `KernelSU: patch syscall 42 failed`，原因 [1.119497] `failed to find phy addr for patch dst addr`。
- [1.119507] **尽管补丁失败，KernelSU 仍记录 `dispatcher installed at slot 42`**。
- [1.125010] sys_enter tracepoint 生效，并注册了 nr=79 `newfstatat`、nr=48 `faccessat` 等。
- [1.125046]、[1.125074] nr=63/read、nr=80/fstat 的直接 Hook 也失败。
- [1.973241] `Run /init as init process`；[1.973923] `init: Could not stat("/"), not freeing ramdisk: Function not implemented`（ENOSYS）。
- [1.974153] `ReadDefaultFstab(): failed to find device default fstab`；
  [1.977556] `reboot: Restarting system with command 'bootloader'`。

**结论：**这是第一阶段 init 的正常故障回退，不是 kernel panic；原版 ramdisk、dtb 在之前静态比对中完全相同。上游 `kernel/hook/arm64/syscall_hook.c` 在补丁 syscall table 失败时仍将 `ksu_dispatcher_nr` 设置为 42，而 `sys_enter` 对被 Hook 的正常系统调用（尤其 `newfstatat`）直接改写为 42，导致执行未被替换的 ni_syscall 返回 `-ENOSYS`。这提供了从实际内核日志到源码实现的高可信因果解释，而不仅是 Clang 版本差异的猜测。

补丁 `scripts/patch_syscall_failclosed_419.py` 使 syscall table 修改失败时不记录成功 Hook，也不发布 dispatcher 编号；`sys_enter` 因编号 -1 自行退出。此补丁**尚未经过新镜像真机验证**；属于保守关闭失效特性，并不能保证 KernelSU Root、Manager、SELinux 正常。

请在回归测试及新内核链接检查完成以前，不提供刷写版本；保留真实失败回归信息。
