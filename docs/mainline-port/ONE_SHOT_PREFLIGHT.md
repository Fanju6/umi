# umi：将剩余 Root 取证合并为一次启动前资料包

**2026-10-17：针对用户希望快速进入 Linux 6.12 首次测试的诉求。** 过去已取得 umi 的 12 个 DTBO 条目、Linux 4.19 最终 FDT 的八条 UFS 供电 phandle、9 条 PMIC 运行状态，以及 P1m **离线** DTS 编译成功证据。这些无需重新采集。

## 一条命令，多个采集项

scripts/mainline_umi_preflight_bundle.py 会先以普通 ADB 验证 device=umi，随后通过授权 Root 在原系统运行只读 shell。一次命令收集：

- 正在运行的内核版本，系统是否已完全启动，非 A/B 状态；Verified Boot 的有限状态字段。
- boot、recovery、dtbo、vbmeta、vbmeta_system、vendor_boot、super 的存在与只读获取的块设备大小。没有读取或备份 userdata。
- pstore/debugfs 是否已挂载，pstore 记录类型（不读取记录正文）；现有 ramoops 模块地址与大小；已暴露的少量 kernel config 和经过白名单过滤的内核 cmdline 键（不采集序列号等敏感启动字段）。
- 对 boot、recovery、dtbo 这三个已经确认存在的分区，**读取完整分区并保存在用户电脑私有文件夹**，逐个验证块设备大小、Boot Header v2 或 DTBO v0 表头，计算 SHA-256，并仅在全部单项检查通过时保留该备份文件。
- 输出脱敏 JSON：只含上述分区元数据、镜像结构数字、校验值、内核接口状态和明确仍未解除的安全门禁。不会上传原始备份、整份 FDT、pstore 日志或任何 userdata。

该程序**不会向手机写入**、不会挂载、重启、执行 fastboot、切换 A/B slot、触发 panic、修改电压，也不会尝试 Linux 6.12 首次启动。备份路径必须在 Git 仓库之外；如果该目录中已有 boot.img、recovery.img 或 dtbo.img，会拒绝覆盖以前的备份。

## Windows PowerShell：一次执行

~~~powershell
cd C:\Users\fanju\umi-p0b
git pull --ff-only
python scripts/mainline_umi_preflight_bundle.py --probe --output "$env:USERPROFILE\Desktop\umi-preflight.json" --backup-dir "$env:USERPROFILE\Desktop\umi-original-images"
~~~

如手机出现 Magisk/KernelSU/APatch 授权框，允许 ADB Shell。这条命令的 Root 部分包含多个独立的只读设备访问，备份总量取决于实际 boot/recovery/dtbo 分区容量。单个分区超过 256 MiB、大小读取失败、镜像头异常会分别记录为失败；命令可能返回退出码 2（不完整的本地备份），但仍会保存诊断 JSON 供下一步定位。

**只上传 umi-preflight.json。不要上传三个原始镜像文件；需要在电脑及另一个可靠存储位置妥善保管，并避免将它们提交 Git。** SHA-256 和独立备份文件可支持以后恢复计划，但**不表示恢复模式本身可启动或能够回刷**。

## 收齐数据 ≠ 可安全刷机

这一次预计足以完成绝大多数仍缺失的 Root 可读“启动前资料”。随后工作应转到：

1. 离线分析并补齐完整 SM8250 umi DTS、适用的 Linux 6.12 驱动、电源时序、两处厂商私有 UFS 投票以及内存 reserved-memory；持续运行 CI 编译/验证，但不将离线研究 DTS 当作现成可启动产品。
2. **单独验证可逆恢复**：在不刷实验内核之前，用独立手段确认 Bootloader/Recovery 真正可进入、当前原始镜像可在需要时可靠恢复，并准备故障日志输出。非 A/B 机器仅有备份和 Recovery Header 并不能构成安全保证。
3. 首次启动尽可能使用经独立验证的临时/可恢复方式，但不能假设 umi bootloader 支持 fastboot boot；这种能力要实测并评估风险。未通过恢复前不能刷实验启动镜像。

不能给出一个保证的剩余“采集次数”：**计划上只剩本次集中采集**，如系统缺失必要接口或备份校验失败才会根据失败项单独补查。后续可能仍有软件驱动/硬件兼容性问题，绝不预先保证一次资料包后立刻安全刷机。

安全门禁仍为 safe_to_attempt_mainline_boot=false、safe_to_flash=false。研究 PR #8 保持 Open、稳定 main 的 4.19 + KernelSU 保持不变。

### 参考

- AOSP Boot Header v2: https://source.android.com/docs/core/architecture/bootloader/boot-image-header
- Android bootimg.h: https://android.googlesource.com/platform/system/tools/mkbootimg/+/refs/heads/main/include/bootimg/bootimg.h
