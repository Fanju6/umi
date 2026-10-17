# umi Root 实机报告交叉分析与剩余阻塞

**2026-10-17。来源：用户上传的由授权 Root 的只读脚本生成的 umi-root-hardware.json。** 仓库只记录技术元数据，不保存原始分区、手机唯一标识或完整文件。

## Linux 4.19 的九条目标 PMIC 电源轨

报告 device=umi；legacy_kernel=4.19.325-cip131-st15-perf-g71b13e62f057-dirty；root_uid_confirmed=true。目标的九条 regulator 均 enabled，运行时设备树的九个 qcom,resource-name 也都有记录：

| regulator | sysfs microvolts | num_users | DT resource |
| --- | ---: | ---: | --- |
| pm8150_s4 | 1800000 | 5 | smpa4 |
| pm8150_l2 | 3072000 | 2 | ldoa2 |
| pm8150_l5 | 880000 | 5 | ldoa5 |
| pm8150_l6 | 1200000 | 2 | ldoa6 |
| pm8150_l9 | 1200000 | 4 | ldoa9 |
| pm8150_l12 | 1800000 | 1 | ldoa12 |
| pm8150_l17 | 2504000 | 1 | ldoa17 |
| pm8150a_s8 | 1200000 | 2 | smpc8 |
| pm8150a_bob | 3296000 | 1 | bobc1 |

这是已运行 4.19 内核的电压/使能状态和旧 DT 资源 ID，num_users 不是独立物理消费者个数。没有由此确认 PCB 上游 parent、电气时序，或 Linux 6.12 PMIC/UFS 驱动正常运作。不得按此直接写入主线板级电压范围、父 supply phandle 或使能禁用的 UFS/USB 硬件。

debugfs_regulator_summary.available=false，可能是对应路径没有挂载/提供，不应直接判为硬件异常。

UFS Host 1d84000.ufshc 的 runtime_status=active、control=auto。PHY 1d87000.ufsphy_mem 的 runtime_status=unsupported、control=auto；后者只描述 runtime PM 接口，不意味着 PHY 坏掉或主线不支持。

## Ramoops 4 MiB 在 /proc/iomem 中被标记为 reserved

本机报告出现两条层级资源：System RAM [0x92700000, 0xB0400000)；其中的 reserved 子区间 [0xB0000000, 0xB0400000)。它与 P1j 的 Ramoops sysfs 基址和长度一致，符合旧 4.19 memblock_reserve 的源码设计。此证据加强实际保留区存在性的支持，但不能证明内存占用方唯一、crash 后日志可靠或 Linux 6.12 可直接复用。

## Boot/Recovery/DTBO

Boot 与 Recovery 均为可读取的 Android Boot Header v2；仅头部可读，不代表 Recovery 已验证可启动或可逆恢复。

旧 Root 检测器将 DTBO 的 AOSP 表头 magic 错误地按小端字节判断为 1eabb7d7。官方 system/libufdt mkdtboimg.py 使用 0xd7b7ab1e 且按 big-endian >8I 写入表头，正确的实际前四字节是 d7b7ab1e。请参阅：

- https://android.googlesource.com/platform/system/libufdt/+/ca387011d3123308b27f0cf2abb72c3819baba4d/utils/src/mkdtboimg.py
- https://source.android.com/docs/core/architecture/dto/partitions

此前的 dtbo=unidentified **不能证明分区损坏**：可能是我们的字节序 bug，也可能是另一种容器/格式，必须重新只读检查。已修复初始扫描器的字节序判断，并补充仅查 DTBO 64 字节头部/现有 debugfs 路径的 Root 脚本；不会保存整分区或执行 mount。

## 下一次只需这一个定向 Root 补充查询

~~~powershell
cd C:\Users\fanju\umi-p0b
git pull --ff-only
python -m unittest discover -s tests -p test_mainline_root_targeted_followup.py -v
python scripts/mainline_root_targeted_followup.py --probe --output "$env:USERPROFILE\Desktop\umi-root-followup.json"
~~~

脚本读取 DTBO 头部 64 字节，在主机内解析官方大端 DT 表、QCDT/FDT 候选或未知签名；只检查已有 debugfs summary 路径是否可读，不挂载、不提取正文。结果保存在本地，不自动上传。

后续重点是确认最终运行 DT / 电源网络与 Linux 6.12 UFS 依赖，再以独立证据验证无风险恢复条件，避免无限地增加重复的非 Root 探针。当前 safe_to_attempt_mainline_boot=false、safe_to_flash=false。

## 2026-10-17 已取得真机补充证据

已收到用户执行 Root 定向探针的完整脱敏输出，确认 DTBO magic=d7b7ab1e、format=android_dt_table、total_size=5514578、header_size=32、entry_size=32、entry_count=12、entries_offset=32、version=0、basic_structure_plausible=true。旧版 unidentified 是实际存在的解析字节序错误。debugfs.already_mounted=false 且 /d、/sys/kernel/debug 的 regulator_summary 均不可用，不证明驱动异常。下一步不需要再反复读 64 字节表头，改为一次性只读解析全部 12 个候选 overlay 的结构，详见 [DTBO 离线分析](DTBO_OFFLINE_INSPECT.md)。所有启动/恢复/刷机门禁不变。
