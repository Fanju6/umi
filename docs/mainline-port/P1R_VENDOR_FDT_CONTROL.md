# P1r：厂商原始 DTB 对照启动（Linux 6.12，仅诊断）

2026-10-17 实际设备 fastboot boot 黑屏、REC 刷 Boot 后短暂 Logo 返回 Fastboot，且两次 Recovery pstore 都未捕获 6.12。

## 云端实验得出的新结论

Run 39019397763 对官方 LineageOS 2026-10-04 umi boot 中原厂 FDT 与 DTBO[11] 做了对照：
- 原厂 DTBO[11] 有 153 个 __fixups__ 依赖，原厂 FDT 全部具备，对应缺失 0 个。
- 现有主线 P1n 只有 11 个必需符号对应，缺失 **142 个**。
- 原厂 FDT 与 DTBO[11] 的 fdtoverlay 离线合并成功；主线 P1n 与 P1q 都失败 FDT_ERR_NOTFOUND。
- 在主线添加 142 个无硬件根据的假设备节点不是有效移植。此项只能证明主机端 FDT 合并结果，并非证明 ABL 实际拒绝或接受。

## 下一步：单变量对照

新增 .github/workflows/mainline-abl-vendor-control.yml：
- 不重新编译内核，复用 Run 39006200229 已验证的真实 Linux 6.12 ARM64 Image，同时重建同样的 RAM-only PID1。
- 使用固定 SHA 的官方 LineageOS 2026-10-04 boot.img，抽出 *确切原厂 FDT*，要求与拆出的 boot DTB 完全一致；另外下载同日原厂 DTBO，并验证条目数、umi model、DTBO 索引 11 的 fdtoverlay 合并成功。
- 将这个原厂 FDT 与 Linux 6.12 Image 和 RAM-only Initramfs 封入 Boot Header v2，严格重新检验 AVB、装载地址、cmdline、每段 SHA256、容量。上传 **umi-Linux612-OFFICIAL-FDT-ABL-CONTROL-NOT-BOOT-VERIFIED**。
- 先前完整 Linux 6.12 主线 P1n 实验作为对照。**两者内核来源相同、静态 /init 相同，仅 DTB 变动**；可协助判断黑屏/返回 Fastboot 是否与 DTBO 兼容相关。

## 风险与范围

原厂 DTB 暴露的是 Linux 4.19 厂商节点，而非已正确移植的 Linux 6.12 板级 DTS。即使 bootloader 能传入该 FDT，Linux 6.12 仍可能早期崩溃、看不到 Ramoops、无法启动任何实用外设。这不是适用于日常的内核，也不是证明能够进入 PID1 的完整移植。通过 CI 只证明镜像结构和离线 overlay 合并，**并不自动授权刷机**。保留独立 TWRP 与本机原始 boot.img；首次对照只能临时 fastboot boot，不能写 recovery/dtbo/vbmeta/userdata。

若对照镜像出现新的 Linux 6.12 pstore，定位转向早期设备树移植；若仍黑屏，仍需更低层的串口/Bootloader 接力证据。私有原始 boot 和 pstore 日志不进入公开 GitHub。
