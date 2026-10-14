# Xiaomi Mi 10（umi）真机只读预检

本项目已完成官方 KernelSU 3.3.0 / LineageOS 23.2 / Linux 4.19 的**内核编译**，尚未验证实际启动、SELinux Enforcing、Root 授权或 Manager 通信。

在电脑安装 Android platform-tools、使用 USB 调试连接**小米 10 umi**，运行：

```bash
bash scripts/device_preflight.sh
```

脚本只读取设备名、Android 版本、LineageOS、内核、SELinux、启动槽位、Verified Boot 状态和相关分区名称是否存在。非 umi 设备立即退出。不读取私密标识、备份或分区内容，也不会获取 Root 或写入分区。

后续进入刷写测试前，必须另外确认：真实运行固件是否与锁定源码一致、原厂 boot.img 的 Header/Ramdisk/AVB 格式、是否 A/B 分区、分区容量、恢复路径以及完整原机备份。尤其要区分 raw `Image` 与可刷写的 `boot.img`，两者不是一回事。

**当前禁止刷写 CI 的编译产物。** 此预检仅为下一阶段真机兼容验证收集非敏感信息。
