# P1g：umi 非 A/B 恢复与早期日志安全门禁

**2026-10-16。只读源码研究；不执行 fastboot、reboot、dd、root、块设备读取或写入。safe_to_flash=false。**

## 已有可靠证据，以及不能由它推导的结论

P0b 真机已观察到 ro.build.ab_update=false、空 ro.boot.slot_suffix，以及 boot、dtbo、recovery、super、vbmeta 等分区名；未看到 vendor_boot 或带 _a/_b 的分区名。这些信息支持当前系统的非 A/B 布局，**但不是独立的启动镜像头解析**。交接资料报告 Boot Header v2，P1g 只记录为已报告、不声称本阶段解析了 boot 镜像。

一个名叫 recovery 的分区并不表示已验证恢复分区可以启动、存在已经核验的原厂备份、Bootloader 可使用临时启动，或者失败后可以恢复到 Linux 4.19。P1g 以上全部保持未验证。

## UART 和持久日志的源码边界

旧版 LineageOS 4.19 Xiaomi common DTS 中，两处 &qupv3_se12_2uart 与 &qupv3_se6_4uart 设置 status = "ok"。这只证明该公开 DTS 具有使能 UART 控制器的语法；未证明 umi 的板级 pinmux、实体引脚、连接器、电平及 earlycon 控制台。不能据此操作未知测试点。

旧版 Kona DTS 保留 res_xbl_uefi_log_region@80880000，它属于 XBL/UEFI 日志相关 reserved-memory，**不是已证实可作为 Linux 6.12 ramoops 的区域**。P0c 已核查的 34 个保留节点不能因日志迁移而改写。

锁定主线 6.12 的 SM8250 SoC DTS 没有直接出现名为 ramoops 的节点；**这不等于主线内核不存在 pstore 支持，也不等于今后不能加入经过实测的板级存储**。

目前仍没有经过证实的 umi Linux 6.12 pstore 跨重启记录保留、earlycon UART 物理日志、或者可供内核早期使用的 USB gadget 日志。目录存在和记录文件名可见，也不足以证明崩溃后可恢复。

## 新增安全工具

1. config/mainline-p1g-recovery-gates.json：记录非 A/B 证据、Boot Header 版本来源、全部未知的恢复与日志环节，以及 false 的实验启动和刷机门禁。
2. scripts/mainline_p1g_recovery_audit.py：离线校验静态合同及 P1e 安全边界。GitHub CI 根据固定 SHA 获取旧 Xiaomi common DTS、Kona DTS、6.12 SoC DTS，执行 UART/日志节点事实核验。不会连接设备。
3. scripts/mainline_p1g_log_probe.py：默认不连接设备；必须明确传入 --probe。只以普通 ADB Shell 查询设备代号、当前内核版本、已完成启动、A/B 属性和 pstore 文件系统的存在性与记录类型。**绝不读取 pstore 日志正文、串号、IMEI、内核 cmdline、原始分区数据，也不 su、adb root、重启、mount 或写 sysfs。**
4. tests/test_mainline_p1g.py：18 项预期回归测试，包括 A/B 假设、声称成功恢复、UART 线路误判、XBL 日志误当 ramoops、模拟 ADB 响应安全性。

## Windows PowerShell：本地验证

仅静态检查，无 ADB：

~~~powershell
cd C:\Users\fanju\umi-p0b
git pull --ff-only
python scripts/mainline_p1g_recovery_audit.py
python -m unittest discover -s tests -p test_mainline_p1g.py -v
~~~

如需要额外实测，可自行选择以下不提权、不重启的只读探针：

~~~powershell
python scripts/mainline_p1g_log_probe.py --probe --output "$env:USERPROFILE\Desktop\umi-p1g-logs.json"
~~~

报告只包含经过白名单处理的技术状态；不得上传含私人数据的原始 pstore 日志。即使 pstore 文件系统已经挂载，pstore_survives_crash_verified、earlycon_verified、recovery_path_tested、safe_to_attempt_mainline_boot、safe_to_flash 也仍然是 false。

## 后续 P1h 的硬性前提

- 板级可真实读取的故障早期日志通路，与 P0c reserved-memory 及最终 FDT 不冲突。
- 恢复分区可用性、原厂恢复镜像、恢复途径各自独立验收；不能通过冒险刷入实验内核来检验恢复能力。
- 六组 PM8150 真正供电 parent、PM8150A S8/BOB 及 P1f 两条 UFS 私有投票仍有待验证，因此硬件和内核启动实验继续禁止。
- 本阶段所有 DTS 保持不变，main 的 4.19+KernelSU 不变，PR #8 继续仅用于研究。

## 固定公开来源

- https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom/xiaomi-sm8250-common.dtsi
- https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom/kona.dtsi
- https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/arch/arm64/boot/dts/qcom/sm8250.dtsi
- 既有实机报告：P0B_REAL_DEVICE_FINDINGS.md；P1f 来源见 P1F_UFS_LIFECYCLE.md
