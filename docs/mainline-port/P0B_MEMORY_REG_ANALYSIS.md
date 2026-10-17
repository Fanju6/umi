# P0b+：umi 实机 reserved-memory 真实范围与 Linux 6.12 对照

**更新日期：2026-10-16 · 状态：14 个选定节点已获得设备树 `reg` 属性；尚非全部 FDT。**

来源：测试者在正常运行的 Xiaomi Mi 10 umi（Android 16 / Linux 4.19.325）通过非 Root ADB Shell 读取 14 个固定白名单 DT 节点的 `reg`、`#address-cells` 和 `#size-cells`，由 Python 将 2+2 个 **big-endian 32-bit cells** 解码为 64 位范围。原始 JSON 由测试者私下提供；仓库只记录不含唯一识别信息的必要技术数据，不上传原始 JSON。主线对照固定到 Torvalds Linux v6.12，SHA `adc218676eef25575469234709c2d87185ca223a` 的 `arch/arm64/boot/dts/qcom/sm8250.dtsi`。

## 设备真实内存布局（半开区间：start 包含、end 不包含）

| 选定 DT 节点 | 真正的 `reg` 起止地址 | 大小 |
| --- | --- | ---: |
| `hyp_region@80000000` | `0x80000000–0x80600000` | 6 MiB |
| `xbl_aop_region@80700000` | **`0x80600000–0x80860000`** | 2.375 MiB |
| `reserved-memory@80860000`（cmd-db） | `0x80860000–0x80880000` | 0.125 MiB |
| `res_xbl_uefi_log_region@80880000` | `0x80880000–0x80894000` | 0.078 MiB |
| `smem_region@80900000` | `0x80900000–0x80B00000` | 2 MiB |
| `removed_region@80b00000` | `0x80B00000–0x85E00000` | 83 MiB |
| `pil_camera_region@86200000` | `0x86200000–0x86700000` | 5 MiB |
| `pil_wlan_fw_region@86700000` | `0x86700000–0x86800000` | 1 MiB |
| `pil_slpi_region@88c00000` | **`0x88C00000–0x8BB00000`** | 47 MiB |
| `pil_adsp_region@8bb00000` | **`0x8BB00000–0x8E000000`** | 37 MiB |
| `pil_spss_region@8e000000` | **`0x8E000000–0x8E100000`** | 1 MiB |
| `cdsp_secure_heap@8e100000` | **`0x8E100000–0x92700000`** | 70 MiB |
| `cont_splash_region@9c000000` | `0x9C000000–0x9E300000` | 35 MiB |
| `disp_rdump_region@9c000000` | **`0xB0400000–0xB1400000`** | 16 MiB |

验证结果：14/14 `observed`，所有区域的 `reg` 格式和长度有效，半开区间严格检查 **0 处内部重叠**，14 区合计 **305.578125 MiB**。不代表另外约 20 个尚未读取 `reg` 的 reserved-memory 节点与这些区之间也绝无重叠，更不能宣称全系统内存保留区的总量仅为 305.58 MiB。

## 两个“名字与 reg 不一致”的真实例子

1. `xbl_aop_region@80700000` 的节点名仍沿用 `@80700000`，但最终生效 `reg` 从 **`0x80600000`** 开始，长度 **`0x260000`**。它恰好与 [主线 Xiaomi elish 的 XBL/AOP 覆盖](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/arch/arm64/boot/dts/qcom/sm8250-xiaomi-elish-common.dtsi#L16-L25) 相同，而不是与主线 SM8250 **默认** `0x80700000/0x160000` 一样。**修正先前仅凭节点名推断“elish 一定不适用于 umi 的 XBL/AOP”这一结论**；但仍禁止复制 elish 整棵 DTS。
2. `disp_rdump_region@9c000000` 节点名为 `@9c000000`，实际 `reg = 0xB0400000/0x1000000`，**与** `cont_splash_region@9c000000` 的实际 `0x9C000000/0x2300000` **互不重叠**。这推翻了上一轮“可能重叠”的疑虑。

这说明至少部分节点名在 bootloader / overlay 影响后不再与实际 `reg` 同步。上述现象本身**不能证明**是哪一级启动链修正了地址；还需要实际基础 DTB/DTBO 的离线差异分析。

## Linux 6.12 的主要不兼容范围（不能直接复用 SoC 默认值）

| 内存用途 | Linux 6.12 SM8250 默认 | umi 实机 `reg` | 后果 |
| --- | --- | --- | --- |
| XBL/AOP | `0x80700000/0x160000` | **`0x80600000/0x260000`** | 默认配置遗漏 `0x80600000–0x80700000` 的实际保留部分 |
| SLPI | `0x88C00000/0x1500000` | **`0x88C00000/0x2F00000`** | 默认只保留 21 MiB，而真实 SLPI 占 47 MiB |
| ADSP | `0x8A100000/0x1D00000` | **`0x8BB00000/0x2500000`** | 主线 ADSP 的前 26 MiB 实际属于 umi 的 SLPI |
| SPSS | `0x8BE00000/0x100000` | **`0x8E000000/0x100000`** | 主线 SPSS 位置实属 umi 的 ADSP |
| CDSP secure heap | `0x8BF00000/0x4600000` | **`0x8E100000/0x4600000`** | 主线 secure heap 有 33 MiB 落在 umi ADSP、1 MiB 落在 umi SPSS |

**重要区分**：上表是“两个备选布局的差异/错误用途相交”，**不是说实际 4.19 运行中的 14 个区域互相覆盖**。错误将主线 SoC 默认 carveout 带入 umi 才可能造成固件启动/内存保护冲突。完整主线 [`sm8250.dtsi` 默认保留区](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/arch/arm64/boot/dts/qcom/sm8250.dtsi#L765-L860)。

## 代码与复现

- [固定 6.12 默认基线](../../config/mainline-612-reserved-memory.json)：18 个 SoC 默认范围及部分同义设备树节点映射，**不是 umi DTS 草案**。
- [离线对照器](../../scripts/mainline_compare_memory.py)：从本地 `umi-p0b-memory.json` 解析原有 14 个范围，检查设备内部重叠，再对照主线默认范围、逐区域差异与跨用途重叠。不联网、不接触设备。
- [原始只读采集器](../../scripts/mainline_reserved_memory_probe.py)：非 Root ADB Shell，只读公开设备树属性，不读取物理内存或 userdata。

Windows PowerShell（在研究分支仓库根目录）：

```powershell
python scripts/mainline_compare_memory.py --report "$env:USERPROFILE\Desktop\umi-p0b-memory.json" --output "$env:USERPROFILE\Desktop\umi-p0b-comparison.json"
```

**暂不进入刷机/引导阶段。** 下一轮工作是以此 **真实 `reg` 布局**为起点制作只含内存及 SoC 核心节点的最小 umi DTS 草案，在隔离环境用 `dtc` / `dtbs_check` 进行验证。先补齐剩余节点的关键保留区范围，并核对 bootloader / 原厂 DTBO 的最终修正规则；未知电源与外设继续保持 `disabled`。

**状态：`P0B_14_REG_OBSERVED`、`P0B_INTERNAL_OVERLAP_ZERO_FOR_SELECTED`、`P0B_UPSTREAM_LAYOUT_INCOMPATIBLE`、`LINUX_612_NOT_BOOTED`、`SAFE_TO_FLASH_FALSE`。**
