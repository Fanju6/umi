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
