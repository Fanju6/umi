# umi Linux 6.12 首次 Fastboot RAM-only 实验：2026-10-17 事后诊断

## 实际首轮启动与恢复操作

- CI Run 39008359041 成功生成 Header v2 实验 boot image；内核 Image、P1n DTB、RAM-only /init 和 AVB/各段 SHA 静态检查全部通过。
- 用户 fastboot boot 临时启动，输出 Sending boot.img (131072 KB) OKAY，Booting OKAY。仅能证明 Bootloader 接受并执行了启动命令，尚不证明 Linux 6.12 成功开始执行。
- 用户随后进入 TWRP：adb devices 报告 recovery，adb shell id -u 返回 0。TWRP ro.bootmode=unknown；它不是否认 Recovery 的有效证据。
- 修复 ADB 调用方式后成功枚举 2 个 pstore 文件和 /proc/last_kmsg 尝试项。

## 对真实上传日志的脱敏结论

上传的原始 console、pmsg 日志包含私有 Android 系统数据，**禁止上传到公开 GitHub**；此文件仅归档不含私密字段的结论。

1. console-ramoops-0.log：260986 B / 3373 行，唯一 Linux banner 是 4.19.325-cip131-st15-perf，来自旧 Android boot。开头确认 Ramoops 0xB0000000 / 4 MiB，已注册 pstore。最后是 reboot: Power down / Powering off the SoC，属于旧 4.19 Android 关机路径，不是 6.12 panic。
2. **新的真实板级启动证据：** console 的旧 Kernel command line 明确包含 androidboot.dtbo_idx=11。这证明本次 4.19 启动确实选中 DTBO 第 11 项，而此前仅证实它是 12-entry 表中唯一 umi model 的候选；不能推出主线 DTB 可安全与原厂 DTBO overlay 组合。
3. pmsg-ramoops-0.log：2097140 B，包含旧 Android 服务与应用日志，不含 Linux 6.12 或 UMI612-MINIMAL-INIT 标记。
4. last_kmsg.log：48 B，内容只是 cat: /proc/last_kmsg: No such file or directory。旧采集器把远端 cat 错误文本算作日志，导致 logs_saved=3；真正有效的是 2 个 pstore 文件。下一版采集器已修为主动拒绝错误文本，并在报告中标识旧 4.19 banner。

## 可证明与不可证明的结论

- **已确认** Fastboot 命令能接受候选镜像、独立 TWRP Recovery ADB root 可访问、pstore 能读到旧 4.19 内核 console/pmsg。
- **未确认** Linux 6.12 是否得到 CPU 控制、完成 DTB 解析、是否初始化 Ramoops、更不用说是否执行最小 /init。三个文件均无 Linux 6.12 banner、无 UMI612-MINIMAL-INIT、无可归属于 Mainline 的 crash stack。
- 无日志可能是 Bootloader-FDT/DTBO 不兼容、内核在注册 pstore 前停止、记录没有跨恢复过程保存等；单凭此次日志不能区分。不能错误宣称 “Linux 6.12 肯定没执行”。
- 下次实验应先提升早期观测能力，并核查 Bootloader 与 umi 主线 DTB/原始 DTBO 的匹配和早期串口/持久日志条件，再使用有具体改动的新候选重新试 boot。不要盲目重复同一镜像。

## 保护的系统边界

这是独立 Boot-only 临时启动研究；不更改原始 recovery、dtbo、vbmeta、userdata；main + KernelSU 4.19 保持不变。用户私人完整 Boot 和日志文件不能提交公开仓库。
