# umi 高版本内核移植 · P0 源码对照

> 状态：**静态研究，未移植、未编译内核、未刷机**。日期：2026-10-16。当前 `main` 的 Linux 4.19 + KernelSU v3.3.1 是已验证基线，保持不变。

**P0b 进展（2026-10-16）：** 已核对 UFS、USB、PMIC 与关键 reserved-memory 公共源码；测试者已提交 umi 的只读实机 JSON，确认实际的 USB 控制器、FTS/充电器/CS35L41 芯片节点和保留内存节点名。见 [真机对照与证据级别](P0B_REAL_DEVICE_FINDINGS.md)、[静态硬件映射](P0B_HARDWARE_MAPPING.md)。**14 个保留内存节点的 `reg` 已通过实机采集验证，0 处内部重叠；主线 SoC 默认 DSP 内存区不适用于 umi**。见 [P0b+ 完整地址对照](P0B_MEMORY_REG_ANALYSIS.md)。Linux 6.12 尚未在 umi 启动。

## 已直接核对的源码

| 轨道 | 固定来源 | 可证事实 |
| --- | --- | --- |
| umi 4.19 BSP | [LineageOS 源码](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/tree/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom) | `umi-sm8250-overlay.dts` 包含 `umi-sm8250.dtsi`、相机配置；根 `compatible` 是 `qcom,kona-mtp` / `qcom,kona`，属于旧版厂商 BSP 命名 |
| Linux 6.12 mainline | [主线 v6.12](https://github.com/torvalds/linux/tree/v6.12/arch/arm64/boot/dts/qcom) | 有 `sm8250.dtsi`、`sm8250-xiaomi-elish-common.dtsi`、`pm8150*.dtsi`，**没有 `sm8250-xiaomi-umi.dts`** |
| Linux 7.0 mainline | [主线 v7.0](https://github.com/torvalds/linux/tree/v7.0/arch/arm64/boot/dts/qcom) | 已有 SM8250 SoC/部分小米板级 DTS，**没有 umi DTS** |
| Linux 7.0 dagu 工程 | [dagu-mainline-linux](https://github.com/Huabin1010/dagu-mainline-linux/tree/7cd802c3daacb0e22ed98a66db08d97dc3dd3855) | `setup-kernel.sh` 克隆 Torvalds `v7.0`，另外添加 dagu DTS、配置、驱动和固件；不是可套用 umi 的完整 Kernel Fork |
| Android 16 GKI | [AOSP android16-6.12](https://source.android.com/docs/core/architecture/kernel/gki-android16-6_12-release-builds) | 存在面向 Android 16 的 6.12 GKI 发行；**它与主线 6.12 是两个需要单独整合的基线** |

这些源码的**精确提交 SHA**和审查文件路径见 [`config/mainline-research.json`](../../config/mainline-research.json)。所有“支持”仅表示相应公开仓库含源码，**不代表 umi 可用**。

## umi 的实际板级差异

- **早期启动**：旧 DTS 的 `qcom,board-id = <43 0>`，以及 `kona-mtp` compatible 不能作为主线 6.12 的成品板级描述。要基于 `sm8250.dtsi` 新建 umi DTS，并从设备当前 FDT 与原厂 boot/dtbo 做只读对照。
- **触控**：umi DTS 确实出现 `st,fts`（I2C @0x49）与 `goodix,gt9889`（I2C @0x5d）两条可能的触控物料路径，支持 FOD。dagu 使用 Himax SPI，并非同一种触控方案；不能假定所有 umi 手机都使用同一个触控供应商。
- **电源和充电**：umi 包含 BQ2597x、IDT P9415、RX1619、LN8282 等专属充电设备和复杂热限制；dagu 的 P9418 是手写笔充电而不是手机 Qi 接收器。不要直接移植 GPIO、电压或充电参数。
- **声音**：umi 有双 CS35L41 扬声器配置。dagu 用四颗 CS35L41 并拥有另一套 Q6 拓扑，能借鉴移植方法但不可复制具体连线。
- **相机**：umi 厂商设备树中有多路 CCI、actuator、EEPROM 与专属 camera sensor 节点。主线 CAMSS 驱动并不自动兼容现有 Android Camera HAL。
- **无线通信**：umi 公共 DTS 有 `bt_qca6390`，dagu 的 ath11k/Wi-Fi 实验说明同代芯片有经验可参考，但固件、board-data 和 WLAN 启动通道仍需对照实机。

## 与 A/B 平板工程不同的分区风险

**umi 为已实测非 A/B、Boot Header v2 的设备**；dagu 的 README 按 A/B 分区、`vendor_boot_b` 和 `set_active b` 设计恢复流程，且 Ubuntu 可能占用 userdata。**绝不能把 dagu 刷机、分区或 rootfs 命令用于 umi。**

这一阶段仅通过 GitHub 公共源码和测试者主动执行的只读 ADB 白名单采集核对设备信息；**不修改设备、不生成刷机镜像**。

## 建议的实施顺序

1. **P0a（已完成：源码目录对照）**：固定 4.19、6.12、7.0、dagu 的 Git 提交，完成优先级设备矩阵。矩阵在 [`config/mainline-research.json`](../../config/mainline-research.json)；本页为人工评估。
2. **P0b（公开源码、实机节点枚举及 14 项 `reg` 范围已完成）**：本地分别克隆固定提交；使用只读 [`scripts/mainline_inventory.py`](../../scripts/mainline_inventory.py) 检查每棵树的 SHA、必要文件及兼容字符串。再从现有 umi 读取设备树/启动分区信息并脱敏对比，禁止刷写。
3. **P1（有足够证据后）**：单独尝试 Linux 6.12 minimal initramfs + USB 串口日志 + UFS 只读枚举；必须先确认真实 recovery 能力与 Pstore/UART，且仅在可恢复试验机上进行。
4. **P2（独立）**：评估 Android 16 GKI 6.12 + 既有 umi Vendor/HAL 的兼容性；禁止因为纯 Linux 能启动便宣称 Android 可启动。
5. **P3**：在新内核能稳定运行 Android 且 SELinux Enforcing 后再重新集成官方 KernelSU；4.19 专属补丁不得直接套用。

## 当前阻塞

- `B0`：umi 主线 6.12/7.0 DTS 缺失；SoC 公共驱动并非完整设备支持。
- `B1`：现有 Android 16 Vendor HAL 与 4.19 专有驱动接口深度耦合。
- `B2`：屏幕和充电器实际硬件料号（多 BOM）尚待独立只读核对。
- `B3`：尚未建立 umi 的高版本最小日志与恢复验证方案。
- `B4`：实机 ADSP/SLPI/SPSS/CDSP secure heap 与主线默认 `sm8250.dtsi` 内存范围冲突，必须用完整最终 FDT 补齐并正确覆盖，不能直接启动主线 SoC DT。

**通过 P0 并不解除以上阻塞，也不能产出可刷写 boot.img。**
