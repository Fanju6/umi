# P0c 完整内存分析与离线 DTS 草案

> **2026-10-16，研究阶段；尚未编译或启动 Linux 6.12，严禁刷机。** 数据源：测试者提供的 Xiaomi Mi 10 umi / Linux 4.19 最终 DT 白名单 JSON。仓库仅保存非唯一的硬件元数据，不保存原始报告或设备识别符。

## 34 个节点实测总结

- 34/34 节点存在。22 个带固定 `reg` 的范围，共 358285312 bytes（341.6875 MiB）；22 个固定区间无重叠。
- 另有 12 个没有固定 `reg`，但有 `size` 的动态内存池，所请求容量合计 365035520 bytes（348.125 MiB）。**请求容量不是当前实际物理占用**，也不能直接加到固定 reserved-memory 内存开销里。
- `secure_display_region` 请求 164 MiB，`mem_dump_region` 40 MiB，`linux,cma` 32 MiB，`cnss_wlan_region` 20 MiB，`qseecom_region` 20 MiB。
- `mailbox_region` 请求 128 KiB（`0x20000`），标记 `no-map`、非 reusable、4 MiB 对齐。与其他 reusable 的动态池不同，不能按照 CMA 池等同处理。
- 动态区域的 `alloc-ranges` 在这份报告中均为从 0 开始、大小 `0xffffffff` 的范围描述；它是分配约束，并不表示动态池已经位于 `0x0`，更不证明它们的最终地址。

## DTS 草案的处理方式

固定 `sm8250.dtsi` v6.12 SoC 基线：无需修改的默认固定保留区继续沿用。umi 实测表明确与默认地址不一致的五组（XBL/AOP、SLPI、ADSP、SPSS、CDSP Secure Heap）先删除默认声明，再按实测 `reg` 重新定义。另外新增四组 umi 特有、原 SoC DTS 没有的固定范围：

| 新增节点 | 实测起始地址 | 大小 | `no-map` |
| --- | --- | --- | --- |
| XBL/UEFI 日志 | `0x80880000` | `0x14000` | 是 |
| Continuous splash | `0x9c000000` | `0x2300000` | **否** |
| DFPS display 数据 | `0x9e300000` | `0x100000` | **否** |
| Display runtime dump | `0xb0400000` | `0x1000000` | 是 |

`cont_splash`、`dfps_data` 不存在 `no-map`，这与有 `no-map` 的绝大多数固件 carveout 不同，应原样保留实测语义，不为了消除 lint 问题强行添加。22 个固定区间及 12 个动态池的真实属性已规范化保存至 [派生清单](../../config/mainline-umi-p0c-memory.json)。

**这份 DTS 仍然不完整：** 12 个动态池暂不复制旧 Qualcomm vendor 专用的 `shared-dma-pool` / secure-memory 绑定。首先需要核对 Linux 6.12 实际驱动是否消费这些 `memory-region` phandles、分配约束以及新的设备树 binding。这不是可以启动 umi 的 DTS，也不参与内核正常 Makefile。

## 离线验证方法

```bash
python3 scripts/mainline_validate_p0c.py
python3 -m unittest discover -s tests -p 'test_mainline_validate_p0c.py' -v
```

新建 `mainline-dts-compile.yml` CI：将托管在 GitHub 的 Linux v6.12 固定 Git SHA 使用稀疏检出获取必要的 Qualcomm DTS 与 `dt-bindings`，用 GNU CPP + `dtc` 真正尝试编译研究 DTS，并用 `fdtget` 读取关键 `reg`。可选的 `dt-validate` 只用于 reserved-memory binding 诊断，不替代完整 Linux `dtbs_check`。**运行成功以前绝不声明 DTS 编译成功**；即使全部成功，也只证明语法/部分 schema，不能证明 bootloader、PMIC、Android 或 KernelSU 适配完成。

后续：逐项审查全部 `memory-region` 消费者、设备启动标识、稳压器、UFS / USB 与 firmware；最小 initramfs 启动的恢复方案尚待制定。保持 `safe_to_flash=false`。
