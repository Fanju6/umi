# P0b：umi 真机只读报告验收（2026-10-16）

> **证据类型：测试者提供的实机 JSON，来自 `scripts/mainline_device_probe.py` 白名单只读 ADB Shell。** 原始文件由测试者上传用于分析，本仓库只保存下述必要的脱敏技术结论，不提交原始分区清单、完整 JSON 或设备唯一标识。此页的“实测”只指**现有 Linux 4.19.325 下的设备信息**，不能证明 Linux 6.12 可启动。

## 运行环境与分区

- `device=umi`，`model=Mi 10`，Android `16`，LineageOS `23.2-20261004-NIGHTLY-umi`。
- 内核 `4.19.325-cip131-st15-perf-g71b13e62f057-dirty`，`boot_complete=1`，SELinux `Enforcing`。
- Root DT：`Qualcomm Technologies, Inc. xiaomi umi`；`compatible=qcom,kona / qcom,kona-mtp / qcom,mtp`。
- `ro.build.ab_update=false`、`ro.boot.slot_suffix` 未返回值；分区名称中有 `boot`、`dtbo`、`recovery`、`super`、`vbmeta`，未观察到 `vendor_boot` 或带 `_a/_b` 的分区名称。**支持当前非 A/B 布局判断，但不是独立的 Boot Header 解析**。不得将 dagu A/B 教程用于本机。

## 公开源码映射获得的真机支撑

| 观察方向 | 设备实际输出 | 现阶段可作的判断 |
| --- | --- | --- |
| USB DWC3 / PHY | `a600000.dwc3`、`a600000.ssusb`、`88e3000.hsphy` | 旧内核实际注册了对应设备，契合主线 `0x0a600000` DWC3 与旧版 `0x088e3000` USB2 PHY 设计；**USB 完整功能尚未测试** |
| UFS 主机 | `ufs_hosts=[]` | **不可推断 UFS 不存在或不可用**，可能是 Linux 4.19 厂商内核没有暴露 `/sys/class/ufs/`。现有 UFS 设备树和磁盘分区说明值得改用 platform/sys/block 路径复核 |
| UFS 电源 | `ufs_phy_gdsc`、`ufs_card_gdsc`、`pm8150_l5/l6/l9/l17/s4` | 与厂商 `xiaomi-sm8250-common.dtsi` 的 UFS regulator 标签吻合；**名称存在不证明启用状态、电压或依赖顺序相同** |
| I2C/板级芯片 | `fts`、`bq2597x-standalone`、`ln8282`、`p9415`、`wl_charger_rx1619`、`wl_rx1619_trim`、`cs35l41` | 当前内核枚举了这些名称；FTS 是本机可观察到的触控候选。未观察到 Goodix **不代表所有 umi 硬件版本均不存在 Goodix** |
| reserved-memory 名称 | 34 个节点（仅名称，没有原始 `reg` 字节） | 能确认该旧内核使用大量板级保留区，**不能依据 `@addr` 后缀推算实际范围与是否重叠** |

## 对 6.12 影响最大的 reserved-memory 差异

以下均为**实机 FDT 节点名称后缀所示地址**，还不是 `reg` 属性验证结果：

| 实机 FDT 节点名 | 名称后缀地址 | 主线 6.12 `sm8250.dtsi` 静态默认值 | 阻塞 |
| --- | --- | --- | --- |
| `hyp_region@80000000` | `0x80000000` | `hyp_mem@80000000` | 初步一致，`reg` 需核查 |
| `xbl_aop_region@80700000` | `0x80700000` | `xbl_aop_mem@80700000` | 初步一致；**elish 覆盖为 `0x80600000`，不可复制** |
| `smem_region@80900000` | `0x80900000` | `smem_mem@80900000` | 初步一致 |
| `res_xbl_uefi_log_region@80880000` | `0x80880000` | 通用主线 DTS 未单独列出 | 必须保护与校验 |
| `pil_adsp_region@8bb00000` | `0x8bb00000` | `adsp_mem@8a100000` | **候选冲突：不能采用 SoC 默认地址** |
| `pil_spss_region@8e000000` | `0x8e000000` | `spss_mem@8be00000` | **候选冲突：不能采用 SoC 默认地址** |
| `cdsp_secure_heap@8e100000` | `0x8e100000` | `cdsp_secure_heap@8bf00000` | **候选冲突：不能采用 SoC 默认地址** |
| `cont_splash_region@9c000000`、`disp_rdump_region@9c000000` | 都以 `0x9c000000` 为后缀 | SoC 主线不存在可靠的 umi 板级映射 | **需要读取真实 `reg` 才能分辨是否别名/重叠** |

旧内核的 `pil_*`、reserved-memory 与 secure firmware carveout 尤其重要；盲目复制通用 SM8250 或 elish DTS，有踩占 TrustZone/DSP 固件内存的风险。不要根据节点后缀直接改 DTS 或内核内存参数。

## 下一步：只读核对 `reg` 属性

后续 P0b+ 的唯一设备操作是从 **14 个固定白名单 reserved-memory 节点**读取设备树中已发布的元数据 `reg`、`#address-cells`、`#size-cells`，由主机 Python 按 **big-endian DT cells** 解码出范围；不读取任何内存内容、boot 分区、IMEI/序列号，亦不提权或写入。若 ADB Shell 权限不足，记录 `unreadable`，不使用破坏性替代方式。

下一阶段必须将上述范围与实际启动时最终 FDT、主线 `sm8250.dtsi` 和 umi bootloader reserved-memory 协议统一核对，确认是否有重叠/遗漏后，才允许构建 **不可刷写的 DTS 草案**。

**状态：`P0B_DEVICE_ID_CONFIRMED`、`P0B_USB_ENUM_OBSERVED`、`P0B_UFS_REGULATORS_OBSERVED`、`P0B_RESERVED_NAMES_OBSERVED`、`P0B_RESERVED_REG_VALUES_PENDING`、`LINUX_612_NOT_BOOTED`、`SAFE_TO_FLASH_FALSE`。**
