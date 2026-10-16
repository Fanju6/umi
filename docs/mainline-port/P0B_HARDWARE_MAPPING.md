# P0b：umi 4.19 → 主线 6.12 关键硬件映射

**状态：公开源码静态核对完成；umi 实机 FDT、驱动枚举与板级参数仍待只读采集。** 不生成镜像、不修改 `main`、不触碰 Flash/EDL 分区。检查日期：2026-10-16。

## 公开代码的实际对应

基线为 [LineageOS umi 4.19（SHA 71b13e6）](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/tree/71b13e62f057a649b77fe4062feb73ee72ad609c)、[Torvalds Linux 6.12（SHA adc2186）](https://github.com/torvalds/linux/tree/adc218676eef25575469234709c2d87185ca223a) 以及只作**对照**的 elish/dagu 板级树。机器可读映射：[`config/mainline-p0b-map.json`](../../config/mainline-p0b-map.json)。

| 项目 | 当前 4.19 源码 | 主线 6.12 | P0b 结论 |
| --- | --- | --- | --- |
| UFS Controller | `ufshc_mem`：`0x01d84000`，SPI 265 | `ufs_mem_hc`：同一地址、IRQ | **SoC 地址相同**；需要重建新 binding 和 clocks/interconnect |
| UFS PHY | `ufsphy_mem`：`0x01d87000` | `ufs_mem_phy`：`0x01d87000` | 基址对应；实际 L5、L9、L17/L6/S4 供电必须重新绑定 |
| 主 USB DWC3 | `dwc3@a600000`：`0x0a600000`，SPI 133 | `usb_1_dwc3`：同一地址、IRQ，父节点 `usb_1@0x0a6f8800` | DWC3 核心对应，PHY、Type-C、电源、HS/SS 角色需单独验证 |
| Hypervisor 内存 | `0x80000000 / 0x600000` | 同 | 静态相同，但还需实机最终 FDT 对照 |
| XBL/AOP 内存 | `0x80700000 / 0x160000` | 同 | **禁止照搬 elish**：elish 改为 `0x80600000 / 0x260000` |
| SMEM 内存 | `0x80900000 / 0x200000` | 同 | 可作为 SoC 级对照，仍需实机核验 |
| XBL/UEFI 日志区 | 4.19 单独保留 `0x80880000 / 0x14000` | `sm8250.dtsi` 不单独声明 | **需要特别保留和审查**：不可因主线漏写而直接覆盖 |
| PMIC/充电 | umi 的 PM8150B、BQ2597x、P9415、RX1619 | PM8150 系列有公共 DTS | 电源域与 regulator 框架可复用，**具体电压/充电策略不可直接移植** |
| 触控与 GPIO | umi 可能使用 FTS@0x49 或 Goodix@0x5d；IRQ GPIO39、Reset GPIO38 | 没有 umi 板级 DTS | 不能使用 dagu 的 Himax SPI 配置；先查实际 BOM |

上游引用位置：[旧 UFS](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom/kona.dtsi#L3054-L3090)、[旧 USB](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom/kona-usb.dtsi#L70-L98)、[旧内存](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom/kona.dtsi#L369-L430)、[主线 UFS](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/arch/arm64/boot/dts/qcom/sm8250.dtsi#L2495-L2585)、[主线 USB](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/arch/arm64/boot/dts/qcom/sm8250.dtsi#L4157-L4220)、[主线内存](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/arch/arm64/boot/dts/qcom/sm8250.dtsi#L765-L857)、[elish 改动](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/arch/arm64/boot/dts/qcom/sm8250-xiaomi-elish-common.dtsi#L16-L25)。

**重要技术边界：** “寄存器地址与 IRQ 相同”只说明同一 SoC IP 在 DTS 中对应，不证明 regulator、clock、pinctrl、IOMMU、firmware 或 Android HAL 已兼容。主线 SoC DTS 中的 UFS 与 USB 节点默认 `status = "disabled"`，需要正确的 umi 板级配置才能启用。此阶段不能生成可刷 Boot。

## 第一次实机只读采集

采集器 `scripts/mainline_device_probe.py` 只通过**未 Root 的 ADB Shell**读取白名单数据：设备/内核版本、Root DT 的 model/compatible、reserved-memory 目录名、分区名称、UFS/USB 枚举与少量 PMIC/触控设备名称。**不会读取**序列号、IMEI、MAC、Android ID、全量 getprop、`/proc/cmdline`、原始 DTB/内存、用户文件，也不运行 Root/写操作。

Windows PowerShell（本仓库研究分支目录下，要求 Python 3 和 ADB 已安装）：

```powershell
adb devices
py -3 scripts/mainline_device_probe.py --output umi-p0b-report.json
```

Linux / macOS：

```bash
adb devices
python3 scripts/mainline_device_probe.py --output umi-p0b-report.json
```

输出仅供本机审查；若要上传至公开仓库，需自行再复核内容。**空字段或无权限不等于硬件缺失**，不能据此禁用驱动。上传者应优先将脱敏报告提供给维护人员作证据分析，而非作为自动代码生成的依据。

## 下一轮判定门禁

1. 与真实运行设备对照 `compatible`、型号、Kernel 及系统版本，确认旧 BSP 的板级事实。
2. 把实机 `reserved-memory` **节点名**与静态 map 对照；地址和大小尚未读取，不能因此认定 carveout 兼容。
3. 确认真实 UFS 主机与 DWC3 控制器至少在旧内核下能够枚举，检查其供电与时钟来源。
4. 在隔离环境中以固定提交获得两份完整源码，生成基于 umi 的 **最小 DTS 草案**；草案中的未知电源、面板、充电节点保持 `disabled`。
5. 通过 DT binding 校验与离线编译后，才讨论带可回滚日志通道的最小引导测试。全程保持 `safe_to_flash=false`。

这里没有做任何真实设备读操作，也没有声称 Linux 6.12 在 umi 上已经启动。
