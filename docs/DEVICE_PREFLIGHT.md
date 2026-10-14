# Xiaomi Mi 10（umi）真机只读预检

本项目已完成官方 KernelSU 3.3.0 / LineageOS 23.2 / Linux 4.19 的**内核编译**，尚未验证实际启动、SELinux Enforcing、Root 授权或 Manager 通信。

在电脑安装 Android platform-tools、使用 USB 调试连接**小米 10 umi**。

Windows PowerShell（无需 WSL）请先下载仓库到本地，在仓库根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\device_preflight.ps1
```

请注意：远程 GitHub 仓库中的脚本不会自动出现在你 Windows 的桌面上。PowerShell 不需要通过 Bash 解释 Windows 路径。

Linux/macOS/WSL（必须另外确保对应环境的 ADB 可以访问手机）执行：

```bash
bash scripts/device_preflight.sh
```

脚本只读取设备名、Android 版本、LineageOS、内核、SELinux、启动槽位、Verified Boot 状态和相关分区名称是否存在。非 umi 设备立即退出。不读取私密标识、备份或分区内容，也不会获取 Root 或写入分区。

后续进入刷写测试前，必须另外确认：真实运行固件是否与锁定源码一致、原厂 boot.img 的 Header/Ramdisk/AVB 格式、是否 A/B 分区、分区容量、恢复路径以及完整原机备份。尤其要区分 raw `Image` 与可刷写的 `boot.img`，两者不是一回事。

**当前禁止刷写 CI 的编译产物。** 此预检仅为下一阶段真机兼容验证收集非敏感信息。


## 2026-10-14 已完成的真机只读核对

真机返回设备 umi、Android API 36、LineageOS 23.2-20261004-NIGHTLY-umi、4.19.325-cip131-st15-perf-g71b13e62f057、SELinux Enforcing。内核 Git 后缀与源码锁定的 71b13e62f057 前缀吻合。

Verified Boot 返回 orange，通常意味着 Bootloader 已解锁；ro.boot.slot_suffix 为空，不能单独证明是否 A/B。请核实真实分区名称（boot、recovery、dtbo 等）和构建参数。

CI #38555215723 已完成整核链接、Image 与 umi 专属 DTBO 校验，但没有可刷机 boot.img，也没有真机 Root 或授权运行时验证。


## 2026-10-14：确认的真实分区布局（脱敏）

Windows PowerShell 真机预检返回：

- 设备 umi，API 36，Android 16，LineageOS `23.2-20261004-NIGHTLY-umi`
- 运行内核 `4.19.325-cip131-st15-perf-g71b13e62f057`，与锁定 Git SHA 的前 12 位匹配
- SELinux `Enforcing`；Verified Boot `orange`
- `ro.build.ab_update=false`；`ro.boot.slot` 和 `ro.boot.slot_suffix` 为空
- `/dev/block/by-name` 存在独立的 `boot`、`recovery`、`dtbo`、`vbmeta`（非 `_a/_b` 后缀分区）

**结论：这部 umi 采用非 A/B、独立 Recovery 的启动布局。** 这不是从空 slot_suffix 单独推断，而是多个系统属性、实际分区名称共同支持。已将不包含序列号、IMEI、账号数据的设备概要保存为 `config/umi_preflight_20261014.json`，并提供 `scripts/check_umi_preflight.py` 可验证它与锁定源码是否吻合。

按照 LineageOS 官方 `device/xiaomi/sm8250-common/BoardConfigCommon.mk`：非 Virtual A/B 构建分支使用 Boot Header v2、页大小 4096、`BOARD_INCLUDE_DTB_IN_BOOTIMG=true`、单独 DTBO；非 A/B 对应的构建参数设定 boot/recovery 分区容量均为 128 MiB、dtbo 为 32 MiB。**这些是源码中的构建参数，不是对当前实际分区大小或现有 boot.img Header 的测量结果。** 进入任何封装阶段前，还必须核对与当前 LineageOS 构建匹配的原始 boot.img/recovery.img，尤其是 header、ramdisk、cmdline、kernel DTB 和 AVB 状态。

绝不能把编译得到的 raw `Image` 用 `fastboot flash boot` 当做 `boot.img`。当前仍未运行 KernelSU 真机版，不能解除 SELinux / Manager 的 P0 阻塞。
