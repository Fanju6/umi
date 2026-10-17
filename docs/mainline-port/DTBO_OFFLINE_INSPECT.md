# umi DTBO v0 实机确认及 12 个 overlay 的离线分析

**2026-10-17。用户使用 Root 只读采集已确认目标系统：Xiaomi Mi 10 umi / Linux 4.19。**

## 已确认的 Bootloader 数据：不需要重复检测 Magic

实际的 DTBO 起始 Magic 为 d7b7ab1e；格式为标准 Android DT Table，表版本为 0，总大小 5,514,578 字节，header size=32，entry size=32，entry count=12，entry offset=32，结构合理。此前出现 unidentified 是我们旧脚本的大端序解析 bug；已修复，分区损坏推测没有依据。

同时确认 debugfs.already_mounted=false、/d 与 /sys/kernel/debug 的 regulator_summary 均不可用。没有运行 mount，也没证明 regulator 驱动没有 debug 接口。与之前 9 条已 enabled 的 PM8150 / PM8150A regulator 和 9 个旧 RPMh resources 证据相容。

这些信息仅确定容器和条目数。按照 AOSP DTBO v0，12 个条目分别记录 id/rev/custom、FDT size/offset。**在不获得条目内容前，不应猜测哪个 overlay 属于本机。** 也不能仅凭表的 id/rev 判断 Bootloader 必然选了哪个条目。

来源：
- https://source.android.com/docs/core/architecture/dto/partitions
- https://android.googlesource.com/platform/system/libufdt/+/ca387011d3123308b27f0cf2abb72c3819baba4d/utils/src/mkdtboimg.py

## 下一步集中任务：一次读取并分析 DTBO

新增 scripts/mainline_dtbo_offline_inspect.py，依用户允许的 Root 权限读取 /dev/block/by-name/dtbo 或 /dev/block/bootdevice/by-name/dtbo 的**最前面 1347 个 4 KiB 块（最多 5,517,312 字节）**，包括完整、已确认大小为 5,514,578 字节的 DTBO 容器。该操作只读且 Root 数据在电脑 Python 进程内存中解析，不落盘原始 DTBO；输出仅包含：

- 12 个 dt_table_entry 的 index、id、rev、custom 四字段、size、offset；
- 每个条目的 FDT 是否能按结构正常解析、root compatible/model；
- overlay 的 fragment target-path；
- UFS/PMIC regulator 相关属性的路径和属性名（不包含 opaque 二进制属性值，不完整转储 FDT）。

**注意**：这是有意识地读取大约 5.5 MiB 的 Root 分区二进制信息，而不是像之前只读 64 字节的脚本一样仅读头；它不会写回分区、重启、改变启动参数、挂载文件系统、提取 pstore 日志或者生成 boot.img。用户应只共享生成的过滤 JSON，而不是原始 image。即使表项全部合法，Linux 6.12 首次启动仍有 UFS PMIC 实际 parent、供电时序以及 recovery 恢复通路等未解决依赖。

Windows PowerShell：

~~~powershell
cd C:\Users\fanju\umi-p0b
git pull --ff-only
python -m unittest discover -s tests -p test_mainline_dtbo_inspect.py -v
python scripts/mainline_dtbo_offline_inspect.py --probe --output "$env:USERPROFILE\Desktop\umi-dtbo-overlays.json"
~~~

如果二进制 ADB exec-out / Root 授权失败，只反馈错误消息即可，不要尝试直接修改分区或启动镜像，也不要用 fastboot flash。

## 数据不能支持的结论

- 12 个条目的 ID/rev/custom 只是厂商分配的硬件版本标识，不足以确定 Bootloader 最终选择；本轮不会声称已重建 bootloader overlay 选择算法。
- 旧 4.19 overlay 供电属性不能照搬成新 6.12 的 PMIC input source，也不能证明硬件 PCB 实际连线。
- Recovery Header v2 已确认，不等于恢复分区能引导或已有验证过的 rollback 机制。
- 当前 safe_to_attempt_mainline_boot=false、safe_to_flash=false，不修改 main 或启用研究 DTS 中禁用的 PMIC/UFS。
