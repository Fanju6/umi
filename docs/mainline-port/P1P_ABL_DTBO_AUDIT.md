# P1p — imi/umi ABL 将 DTBO[11] 应用于主线 DTB 的离线验证

2026-10-17 真实设备在 fastboot boot 接受 128 MiB Boot v2 后黑屏，TWRP 刷入重启则短暂 Mi Logo 后进入 Fastboot。两次 TWRP pstore 留下的都是 4.19 系列 Linux Android/Recovery 日志，均没有 6.12 banner、P1n /init marker 或主线 kernel panic。

**这并不能证明 6.12 从未开始执行。** 但引导前 DTB/DTBO 合并是必须排查的第一项，因为：
- Android 官方 DTBO 设计要求引导程序将板级 DTBO 覆盖在 Boot 内的 SoC 基础 DTB 上，失败可能发生在内核交接前。
- 实测旧系统启动参数含 androidboot.dtbo_idx=11，公开厂商 DTBO 容器有 12 项，索引 11 是 umi，说明确实存在这个被选中的覆盖层。
- P1n 原先只确认自身能由 dtc 编译及六类硬件保持 disabled，**从未与厂商索引 11 overlay 执行真实合并**。
- Linux 6.12 sm8250.dtsi 跟厂商 4.19 FDT node/symbol/phandle 结构差异可能导致兼容性问题。

因此新增单独 CI：
.github/workflows/mainline-abl-dtbo-audit.yml

流水线全自动使用：
1. 首次成功编译的固定 Linux 6.12 Image + P1n DTB Artifact、SHA256SUMS 检查（Run 39006200229）。
2. 公开、固定 SHA-256 的 LineageOS umi 2026-10-04 Boot，解出其原始 vendor base DTB。
3. 同一公开发布目录的 dtbo.img，校验 Android DT table v0，12 项并核实第 11 项含 umi model 字符串。
4. 用 Linux device-tree-compiler 的 fdtoverlay，对原始 vendor base DTB 和 Mainline P1n DTB **分别尝试应用同一个 umi DTBO[11]**，形成小型 JSON 报告：合并是否成功、工具退出码、脱敏后的有限错误信息。不会把原始厂商 DTB、全部板级树或用户隐私上传至 Artifact。

这份 CI 是下一版实验镜像制作前的诊断门：如果 P1n 合并失败，先按真正缺失的符号/目标修复 DTB；如果厂商 base 也失败，则要检查 DTBO 的发布日期与当前设备映像是否匹配。若公版文件布局不一致则报告而不隐瞒。

该流程不构建 boot.img、不写任何手机分区、不碰稳定 main，也不需要用户再运行 root 取证。确认兼容性后，再决定是否云端打包下一版 P1p Boot。


## P1q additive bootloader-symbols diagnostic

在固定厂商 kona.dtsi 中确认两个标签:
- arch_timer: timer，现有 Linux v6.12 sm8250.dtsi 根节点有 timer，但没有 arch_timer 标签。仅为其增加该标签，不覆盖内核的 PPI/interrupts。
- qcom_tzlog: tz-log@146bf720，固定厂商中该节点的物理基址是 0x146bf720。P1q 添加同名标签和 reserved 映射身份，但 status=disabled，不激活 vendor-specific log driver。

这两个标签亦在 2026 年 Qualcomm ABL / DTBO 引导失败的上游讨论中出现。但其他 SoC 的问题**不是** umi 设备的确定诊断。新 P1q 不能随便宣传已经解决黑屏。

CI 必须同时比较原本 P1n 和额外 shim P1q 的二进制 FDT，通过 fdtget 检验 __symbols__，定时器 interrupts 与 P1n 字节对照一致，全部 UFS/USB disabled，然后分别 fdtoverlay 尝试跟同一个公版 vendor umi DTBO index11 合并。结果如果 P1q 有明确改进，下一步再考虑云端打包新候选镜像。不修改稳定 main 或手机任何分区。
