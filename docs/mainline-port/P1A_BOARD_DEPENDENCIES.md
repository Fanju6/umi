# P1a：umi UFS / USB / PMIC 与 reserved-memory 消费者对照

> **研究分支状态：已具备可离线编译的 P0c 内存 DTS；P1a 仅建立新的板级依赖对应关系，不使能硬件、不生成 boot.img。** `main` 中 Linux 4.19 + KernelSU v3.3.1 不改动。

## 锁定来源

- [Torvalds Linux v6.12 `sm8250.dtsi`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/arch/arm64/boot/dts/qcom/sm8250.dtsi) (`adc218676eef25575469234709c2d87185ca223a`)
- [umi / LineageOS 4.19 `xiaomi-sm8250-common.dtsi`](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom/xiaomi-sm8250-common.dtsi) 和 [`umi-sm8250.dtsi`](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom/umi-sm8250.dtsi)、[`kona-usb.dtsi`](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom/kona-usb.dtsi) (`71b13e62f057a649b77fe4062feb73ee72ad609c`)
- Linux v6.12 [elish board DTS](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/arch/arm64/boot/dts/qcom/sm8250-xiaomi-elish-common.dtsi) 提供参考写法，**不是 umi 供电参数的来源**。

## 首批必须处理的板级依赖

| 模块 | 主线 6.12 标签 / 物理地址 | umi 4.19 已确认事实 | P1a 动作 |
| --- | --- | --- | --- |
| UFS HCI | `ufs_mem_hc`，`0x01d84000`，SPI 265 | `ufshc_mem`，VCC L17 / VCCQ L6 / VCCQ2 S4；额外 `vddp-ref-clk`、父供电 | 保持 disabled，审核新绑定、clock/power-domain/IOMMU 与 regulator |
| UFS PHY | `ufs_mem_phy`，`0x01d87000` | PHY L5、PLL L9；独立的电流负载要求 | 保持 disabled，禁止直接把旧驱动专有属性复制到主线 |
| USB 1 wrapper | `usb_1`，`0x0a6f8800` | 旧版 `usb0`；父节点/IRQ/clock 描述不同 | 保持 disabled，审核 VBUS、Type-C 与 PD 角色切换 |
| DWC3 | `usb_1_dwc3`，`0x0a600000`，SPI 133 | 旧版 `dwc3@a600000`，共用 DTS 将最高速度限制为 High-Speed | 保持 disabled，重新审计 DWC3 PHY 组合 |
| USB2 HS PHY | `usb_1_hsphy`，`0x088e3000` | `usb2_phy0`，旧内核需要具体 PHY override，涉及 PM8150 L5/L12/L2 | 保持 disabled，避免提前复制旧寄存器调校 |
| USB3 QMP PHY | `usb_1_qmpphy`，`0x088e8000` | 旧公共设备树明确关闭 `usb_qmp_dp_phy` | 保持 disabled，不以同 SoC 为由假设 USB3 正常 |

**主线已经提供 SoC IP、GCC/GDSC、Interconnect、IRQ、SMMU 等基础描述；尚缺的是可在 umi 上验证的 `pm8150*` regulator、实际供电范围、充电与 USB 端口接线。** P1a 不给这些节点赋上来自 elish 的未经验证的稳压器 phandle，也不把任何节点改成 `okay`。

## memory-region 消费者必须一起验证

固定的主线 `sm8250.dtsi` 存在下列直接 `memory-region` 引用：
- `smem_mem` → SMEM 通信；
- `gpu_mem` → GPU zap；
- `slpi_mem` → SLPI remoteproc；
- `cdsp_mem` → CDSP remoteproc；
- `video_mem` → Venus 视频固件；
- `adsp_mem` → ADSP remoteproc。

P0c 已删除并重建 `slpi_mem`、`adsp_mem` 这类标签；新草案必须保证原有 phandle 消费者在 **编译后的 DTB** 中仍然正确解析，且未来启用 DSP 前确认 firmware 与最终 `reserved-memory`。不能将旧 BSP 的 `memory-region` 引用原样挪到不相容的 GKI/HAL 上。

## 代码成果与验收

- [P1a 设备树草案](../../research/mainline/sm8250-xiaomi-umi-p1a.dts)：包含 P0c 内存草案，明确将 6 个控制器/PHY 节点保持 `disabled`。
- [机器可读证据矩阵](../../config/mainline-p1a-dependencies.json)：每个控制器的物理地址、旧版供电/限制、固定来源及下一步门禁。
- [P1a 锁定源码审计](../../scripts/mainline_p1a_audit.py)：扫描真实 `sm8250.dtsi` 和旧版 umi 的三个文件，验证标签、寄存器、供电字符串与六组 `memory-region` 消费者。
- [测试](../../tests/test_mainline_p1a.py) 与 CI：核对所有节点保持 disabled，独立编译 P1a 暂时 DTB，检查 `status`，不产出可刷写镜像。

## P1b 的门槛

1. 用实机 **只读数据**核对 umi 运行时 PMIC 供电电压/状态、USB Type-C/VBUS/USB2 HS PHY，建立 regulator 名称与主线 GPIO/PMIC pinctrl 对应。既有 UFS 启动正常不代表主线可直接启用。
2. 需要板级 `pm8150.dtsi`、`pm8150b.dtsi`、`pm8150l.dtsi` 与真正核验的 RPMh regulator 描述；不能直接照搬平板供电。
3. 做各 `memory-region` 的 DTB phandle 回归，并核对 Android 16 vendor/firmware 与内核接口。
4. 仅在拥有可靠 UART/Pstore/USB gadget 日志和恢复路径后，再规划最小 UFS 只读启动；在此之前保持 `safe_to_flash=false`。

**当前门禁：`P1A_SOURCE_MAPPED`、`P1A_DRIVERS_NOT_ENABLED`、`NO_BOOT_IMAGE`、`NO_612_DEVICE_TEST`。**

## P1a 实际 CI 验证（2026-10-16）

[Actions #38865386729](https://github.com/Fanju6/umi/actions/runs/38865386729) 已完成并返回 success，运行内容包括：

1. 以锁定 SHA `adc218676eef25575469234709c2d87185ca223a` 稀疏检出 Linux v6.12 的 SM8250 DTS；通过 pinned URL 下载 `71b13e62f057a649b77fe4062feb73ee72ad609c` 的 umi 4.19 厂商 DTS 并验证真实标签、供电描述和六个主线 `memory-region` 消费者。
2. 执行 P1a 清单与安全回归，全部通过。P0c DTS 保持可编译。
3. 对 `sm8250-xiaomi-umi-p1a.dts` 真实执行 GNU CPP → `dtc`，生成**临时离线 DTB**。通过 `fdtget` 回读 UFS HCI、UFS PHY、USB1 wrapper、DWC3、USB2 HS PHY、USB3 QMP PHY 的最终 `status`，**六个都是 `disabled`**。
4. Reserved-memory 的受限 Schema 诊断步骤成功。此步骤**不是完整 `dtbs_check`**，也不证明任何硬件已在 Linux 6.12 下初始化成功。

安全状态不变：`safe_to_flash=false`、`bootable=false`、`no_boot_image`。当前没有在 umi 真机测试 Linux 6.12，所有供电参数仍待单独 P1b 实机核验。
