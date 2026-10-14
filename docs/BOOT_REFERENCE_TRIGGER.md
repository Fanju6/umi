# 2026-10-04 umi 原版 boot.img 离线结构审计

设备：Xiaomi Mi 10 `umi`，LineageOS `23.2-20261004-NIGHTLY-umi`，已由用户提供只读的设备信息。

原版 boot 镜像官方链接：

https://mirrorbits.lineageos.org/full/umi/20261004/boot.img

## CI 自动审计范围

1. 在 GitHub Actions 中下载官方 `boot.img`，校验二进制 `ANDROID!` 魔数、镜像体积上限和 SHA-256。
2. 只读解析 Android Boot Header v0-v2，打印并核对 Header v2、4 KiB 页大小、Kernel / Ramdisk / DTB 分段、启动参数及是否存在 AVB Footer 魔数。
3. 把结构报告和 SHA-256 上传为 CI Artifact。**不上传原版或修改版内核镜像，不生成、不刷写 boot.img**。
4. 即使报告成功，SELinux 与 Manager 真机 P0 门禁仍保留。

## 后续封装需要的额外检查

- 本次解析核实 header、ramdisk、cmdline、Kernel、DTB 的真实布局后，才设计内核替换。
- ROM 自带的 AVB、dtbo 与 recovery 可能有额外校验，不推测这些格式；不要直接烧写原始 `Image`。
- 想刷测试版本前，必须有同版本原始 boot/recovery、确认 USB/Fastboot 恢复可用并单独评估镜像构建和 SELinux 的风险。

## 重新触发

GitHub Actions 可手动运行「官方 umi boot.img 只读结构审计」。也可以更改此文件重新触发。
