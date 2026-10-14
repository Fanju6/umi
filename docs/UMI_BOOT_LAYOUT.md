# umi / LineageOS 23.2 启动镜像验收约束

## 已有证据

真机读取表明：`umi`、Android API 36、LineageOS `23.2-20261004-NIGHTLY-umi`、内核版本 `4.19.325-cip131-st15-perf-g71b13e62f057`、SELinux `Enforcing`、`ro.build.ab_update=false`、无启动槽位，以及 `boot`/`recovery`/`dtbo`/`vbmeta` 独立分区。

上游 `sm8250-common/BoardConfigCommon.mk` 表示旧版非 Virtual A/B 条件下使用 Boot Header v2，4 KiB 页，启用将 DTB 纳入 boot image，同时设备 DTBO 单独分区。

**这仅支持选择封装技术路线，不代表当前线上 boot.img 的格式、分区容量、AVB 签名及 Ramdisk 可以靠推测确定。**

## 进入 boot.img 封装之前必须完成

1. 获取与手机目前运行的 20261004 LineageOS 固件**精确对应**的原始 `boot.img`；若系统包提供 recovery.img，也要保留原件作为恢复参考。先做本地 SHA-256。
2. 用支持 AOSP boot header 的工具**只读解析**原始 `boot.img`，明确 Header v2 是否成立、Kernel/Ramdisk/DTB 布局、cmdline、大小和 AVB 尾部数据。
3. 核对设备真实分区的大小与恢复操作方案，不用源码中 `BOARD_BOOTIMAGE_PARTITION_SIZE` 直接代替真机读数。
4. 制定 SELinux Enforcing 下的 SID/AVC 事务回滚及 Android 16 Manager 握手测试；二者仍为阻塞。
5. 由可审查的打包过程输出可测试镜像，**不得发布、自动刷写或在现有真机上先行覆盖 boot/recovery**。

## 自动校验

```bash
python3 scripts/check_umi_preflight.py config/umi_preflight_20261014.json
```

通过此检查仅表示设备报告、源码前缀与非 A/B 分区布局一致；输出始终包含 `safe_to_flash=false`。CI 继续将 `selinux-abi` 和 `manager-handshake` 标记为 BLOCK。
