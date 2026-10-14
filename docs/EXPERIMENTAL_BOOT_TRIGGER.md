# Xiaomi Mi 10 umi · 官方 KernelSU 3.3.0 实验性 boot.img 构建

**实验风险：内核已经编译成功，但从未在当前 Android 16 真机启动。SELinux、SID/AVC、Manager/Seccomp 仍未通过运行时验收。实验可能导致设备无法启动，且无法保证恢复过程没有数据损失。**

本工作流使用用户当前相同的 LineageOS `23.2-20261004-NIGHTLY-umi` 官方原版 boot.img：
https://mirrorbits.lineageos.org/full/umi/20261004/boot.img

已由只读 CI #38566227406 核实：
- 原版 SHA256：`ce4a917a9233921b03e748b1fffc7b5ecea613c7ddf72208f26c77189f31a693`
- Boot Header v2；4KiB page，128MiB 大小。
- 原版 Ramdisk 1,494,000 字节，DTB 1,424,944 字节；必须保持它们 SHA-256 不变。
- AVB Footer：`Algorithm NONE`、Hash sha256、分区 boot；原版携带 Android 16 和构建指纹属性。

新 CI `.github/workflows/experimental-boot.yml`：
1. 从 pinned LineageOS 与官方 KernelSU v3.3.0 重新编译完整内核。
2. 校验下载的原版 SHA-256；调用 LineageOS 的 unpack_bootimg/mkbootimg 保留原版 Ramdisk/DTB/启动参数，替换 Kernel。
3. 重建 AVB Hash Footer（算法 NONE，重新计算摘要），保留同版 fingerprint、Android 版本、原 boot 分区尺寸。
4. 自动比较原版/实验版 Kernel、Ramdisk、DTB、Header、cmdline、AVB 字段；任何不匹配都不上传镜像。
5. 严格校验通过后，将临时 `EXPERIMENTAL-UNVERIFIED` ZIP 保存于 Actions Artifacts，**不会刷机、不会发布 Releases**。

重要：`safe_to_flash=false` 始终保留，即使镜像结构验证通过。ROM 运行时、SELinux 强制模式及 KernelSU Manager 均尚未验证。实验前须准备完全匹配的原版 boot.img、确认 Fastboot/Recovery 能访问，并对个人数据做备份；**用户拥有解锁 Bootloader 并不代表所有失败都必然无损恢复。**
