# P0c · 34 个内存节点核验与 Linux 6.12 DTS 骨架

**阶段：只读 P0c；不涉及 Root、刷机、Linux 6.12 开机或 Android 16 迁移。**

## 已获得的技术证据

- 用户首份 umi 实机报告列出了 **34 个 reserved-memory 子节点**。
- 第二份报告验证了其中 **14 个真实 `reg` 区间**，相互无重叠；尚余 **20 个**缺少实际 `reg` / `size` 等元数据。
- [Torvalds Linux v6.12 的 elish 板级 DTS](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/arch/arm64/boot/dts/qcom/sm8250-xiaomi-elish-common.dtsi) 中，XBL/AOP、SLPI、ADSP、SPSS、CDSP Secure Heap 五组地址和大小与 umi 已测值**完全一致**。这是高质量板级参考，但两设备的 panel、touch、PMIC 电源布线和 bootloader 选择不可互换。

## 新增成果

1. [34 节点只读报告工具](../../scripts/mainline_full_reserved_probe.py) 对之前实机列出的完整名称白名单，读取 `reg`、`size`、`alignment`、`alloc-ranges`、`no-map`、`reusable` 等 DT 属性。Linux CMA 等动态分配池可能**没有 `reg`，只有 `size`**，这不是缺失或失败。工具只能报告固定区间的重叠；标记疑似重叠是人工复核事项。
2. [Linux 6.12 umi P0c DTS 草案](../../research/mainline/sm8250-xiaomi-umi-p0c.dts) 以 `sm8250.dtsi` 为起点，**仅**删除并重建上述五组已测量的 carveout；所有其余外设仍维持主线默认状态，未配置完整的 PMIC、DDR/DDR carveouts、启动 ID、存储与显示。**不能用来启动 umi，也没有经过完整 DTS 编译。**
3. [单元回归](../../tests/test_mainline_p0c.py) 验证 34 节点白名单、动态 CMA、big-endian、重复/缺失字段拒绝、错误设备拒绝和 DTS 非刷机边界。

## 采集后如何继续

在已经拉取 `research/sm8250-mainline-p0` 的 Windows PowerShell 中：

```powershell
cd C:\Users\fanju\umi-p0b
git pull --ff-only
python scripts/mainline_full_reserved_probe.py --output "$env:USERPROFILE\Desktop\umi-p0c-memory.json"
```

脚本使用**非 Root 的 ADB Shell**，只读旧内核向用户空间公开的设备树元数据。无需安装额外依赖，不读取内存内容、设备唯一识别码或分区数据，也不会把报告上传到 GitHub。建议先检查 JSON 后再分享。

收到第二轮补齐的 20 个节点后，依据实机 `reg` 区间与动态池 `size`、`alloc-ranges` 做全 34 节点的内存地图并对比 Linux 6.12 的默认 carveout，之后再进入 DTS 的 `dtc` 和 `dtbs_check` 实际编译阶段。

**门禁：`P0C_DTS_OFFLINE_ONLY`，`FULL_DTB_NOT_VERIFIED`，`SAFE_TO_FLASH_FALSE`。**
