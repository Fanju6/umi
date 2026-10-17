# umi 高版本内核移植 · P0 源码对照

> 状态：**静态源码研究及非刷机 DTS 离线编译已通过；未编译高版本内核、未在手机启动、更未刷机**。日期：2026-10-16。当前 `main` 的 Linux 4.19 + KernelSU v3.3.1 是已验证基线，保持不变。

**P0b 进展（2026-10-16）：** 已核对 UFS、USB、PMIC 与关键 reserved-memory 公共源码；测试者已提交 umi 的只读实机 JSON，确认实际的 USB 控制器、FTS/充电器/CS35L41 芯片节点和保留内存节点名。见 [真机对照与证据级别](P0B_REAL_DEVICE_FINDINGS.md)、[静态硬件映射](P0B_HARDWARE_MAPPING.md)。**14 个保留内存节点的 `reg` 已通过实机采集验证，0 处内部重叠；主线 SoC 默认 DSP 内存区不适用于 umi**。见 [P0b+ 完整地址对照](P0B_MEMORY_REG_ANALYSIS.md)。Linux 6.12 尚未在 umi 启动。

**P0c 进展（2026-10-16）：** 已建立 [34 节点白名单采集器、Linux 6.12 umi 非刷机 DTS 草案及回归门禁](P0C_DTS_DRAFT.md)。34 个节点的属性已经全部采集并核对：22 个固定区间（341.6875 MiB）与 12 个动态池（请求容量 348.125 MiB）。[最新内存分析与 DTS 验证](P0C_FULL_MEMORY_AND_DTC.md) 已记录真实 CPP/dtc/fdtget 编译通过，但绝不表示可在 umi 上启动。

**P1a 进展（2026-10-16）：** 已编写 [UFS / USB / PMIC 与 `memory-region` 板级依赖对照](P1A_BOARD_DEPENDENCIES.md)。单独 DTS 草案把六个控制器和 PHY 显式保持 `disabled`，不填写未确认的 regulator 接线；随后将通过锁定源码审计及真实 DTS 编译验证。这并不代表 Linux 6.12 已能开机。

**P1b 进展（2026-10-16）：** 已建立 [PM8150 供电与 Type-C 源码及实机核验](P1B_POWER_TYPEC.md)，第二份真实 umi P1b 报告观察到 **56 条稳压器记录，其中 UFS/USB2 PHY 所需的 7 条实体电源轨均已启用**。已将七轨脱敏快照与八条旧 DTS 供电关系关联并加入离线回归；安全电压、上游 phandle/供电时序、Type-C/PD 新版驱动仍未验证，`safe_to_flash=false`。

**P1c 进展（2026-10-16）：** 已建立 [PM8150 七条实体输出轨与六组主线 RPMh 父供电属性的对照](P1C_RPMH_TOPOLOGY.md)。P1c 离线研究 DTS 继承 P1a，只含 `disabled` 的示范性 regulator provider；父供电 phandle、电压配置和 UFS/USB 硬件仍然全部禁用。这是输入拓扑建模，尚非可用的板级供电配置。

**P1d 进展（2026-10-16）：** [锁定 umi 4.19 Kona VRM 资源](P1D_VRM_EVIDENCE.md) 明确 PM8150 七条电源轨使用 `ldoaN/smpa4`（资源 ID 后缀 `a`）。另外补齐 UFS 厂商专有的参考时钟供电与 VCCQ 上游 parent 两条依赖。主线 PMIC ID 候选置信度提高，但仍未经 Linux 6.12 真机探测，父供电与电压设置继续未知。


**P1e 进展（2026-10-16）：** [UFS 父供电 / PM8150A S8、BOB 资源审计](P1E_UFS_PARENT_AUDIT.md) 从锁定 4.19 证实 smpc8/bobc1，对照 6.12 PM8150L 驱动模板；补齐 Host/PHY clock、reset、power-domain、IOMMU 和 ICC 的依赖矩阵。六组父供电 phandle 仍未知，两条 UFS 私有投票尚不能替换；新增固定 SHA 源码交叉核验和安全回归，原 DTS 全部禁用。


**P1f 进展（2026-10-16）：** [旧 UFS 特殊 regulator 生命周期审计](P1F_UFS_LIFECYCLE.md) 进一步核对固定 Linux 4.19 UFS driver 的初始化、Link OFF、Hibern8 与恢复：vddp-ref-clk 有实际 enable/disable；vccq-parent 是带 auto BKOPS 条件的负载投票，而非直接 enable。S8C 还被旧 WLAN/BT DTS 消费引用。对比主线 Linux 6.12 的标准 regulator 处理，两个额外 Vendor 投票仍未完成电气等价审查，继续禁止使能硬件。


**P1g 进展（2026-10-16）：** [umi 非 A/B 恢复与早期日志安全门禁](P1G_RECOVERY_LOG_GATES.md) 将 P0b 的分区布局观察、旧 DTS UART 控制器启用、XBL/UEFI 保留日志区与真正能用的串口/Pstore 区分开；新增只读可选探针、18 项单测和固定 SHA 跨源码 CI。未验证恢复镜像、Recovery 可用性、实体 UART/earlycon、pstore 跨故障保留。当前仍不允许尝试主线启动或刷机，且不修改既有 DTS。


**P1h 进展（2026-10-16）：** [umi 实测 Pstore/Ramoops 摘要及 6.12 源码对照](P1H_PSTORE_EVIDENCE.md) 确认现有 4.19 系统可挂载 Pstore，用户只读探针可见 `console-ramoops*` 与 `pmsg-ramoops*` 两类记录，但未验证跨重启/崩溃保留、实际 RAM 后端及内存地址。对比主线 6.12 的 `fs/pstore/ram.c` 与 `ramoops.yaml`，保留所有供电、物理地址、恢复及刷机门禁；新增本地完整脱敏报告校验、负向测试和固定源码 CI。


**P1i 进展（2026-10-16）：** [旧 4.19 Pstore 注册路径的只读证据探针](P1I_RAMOOPS_REGISTRATION.md)：P0c 实测的 34 个 reserved-memory 节点里没有名为 `ramoops` 的节点，但 P1g/P1h 已确认当前旧内核挂载 Pstore 并暴露 `console`/`pmsg` 记录。新增不提权、必须显式执行的设备元数据探针及离线回归，只观察 platform device / DT compatible / 内核参数目录存在性，不读取物理地址、日志正文或分区。不改变任何 DTS 与启动/刷机安全门禁。


**P1j 进展（2026-10-16）：** [旧 BSP Ramoops 的固定候选内存地址与 P0c 冲突核查](P1J_RAMOOPS_MEMORY.md)：锁定 4.19 的 `sm8250-common.config` 配置 `ramoops_memreserve=4M`，`fs/pstore/ram.c` 使用 `memblock_reserve` 和平台设备注册，源代码候选为 `0xB0000000` 的 4 MiB；与 P0c 已记录的 22 个固定内存区零重叠，紧邻 `0xB0400000` 的显示 dump 区，但 12 个动态池及运行时参数仍待查。提供可选非 Root sysfs 数字元数据探针、源码锁定 CI 和拒绝不安全使能的回归测试；继续禁用主线启动/刷机。


**P1k 进展（2026-10-16）：** [umi 4.19 实测 Ramoops 四参数及主线 6.12 迁移安全门禁](P1K_RAMOOPS_MIGRATION.md) 确认用户的非 Root 真机参数 `0xB0000000`、4 MiB、console 2 MiB、pmsg 2 MiB 均与旧驱动一致，且本地完整脱敏报告验证通过。修复 P1j 运行时证据标志随 `--report` 动态导出；主线内存所有权、动态池、故障恢复等仍未知；未改任何 DTS、未生成启动镜像、仍禁止刷机。


**P1l 进展（2026-10-16）：** [六组 PM8150 上游供电属性的 schema 与真实布线区别](P1L_REGULATOR_PARENT_GATES.md)：固定主线 6.12 的 RPMh binding 仅强制要求 `compatible` 与 `qcom,pmic-id`，允许的六组输入供电字段并非全部标记 required；驱动 `supply_name` 把七个输出轨归入六组。强调 DTS 语法通过**不代表**真实 parent、电气时序或 UFS 供电安全。六组 parent 仍为 null，两条 Vendor UFS 额外投票仍未迁移，研究 DTS 全部 disabled，不执行硬件操作或刷机。


**Root 快速基线（2026-10-16）：** 用户明确允许通过 Root 加快 umi 旧系统硬件取证，新增 [一次性 Root 只读硬件采集](ROOT_HARDWARE_SURVEY.md)：集中检查 PMIC regulator、已有的 debugfs 供电层级、运行时设备树的受限 RPMh 资源标识、`/proc/iomem` 中 Ramoops 相交区间、UFS runtime PM 和 Boot/Recovery/DTBO 最前 64 字节的头部元数据。脚本不重启、不刷机、不写分区，不挂载 debugfs，也不采集私人数据；仅将过滤后的 JSON 保存在本地。旧系统 Root 元数据依然不足以证明 Linux 6.12 的供电接线和恢复能力，所有安全门禁不变。今后优先集中验证实际阻塞项，不再为同类非 Root 属性逐个拆阶段。


**Root 报告实测结果（2026-10-17）：** [九轨 UFS/PMIC 元数据与 DTBO 字节序复核](ROOT_BASELINE_FINDINGS.md) 确认 9 个目标电源轨均 enabled、9 个对应 RPMh 资源在运行时设备树存在、UFS Host runtime active、/proc/iomem 有与 4 MiB Ramoops 完全一致的 reserved 子区间；Boot/Recovery Header v2 已读取。原 Root 工具 DTBO magic 判断字节序错误，已改为 AOSP 标准大端解析，添加精简只读后续探针及回归测试。**仍未知真实上游电路连线和 Recovery 可逆性，不能试启动/刷机。**


**DTBO 实机复核（2026-10-17）：** [已确认标准 Android DT Table v0 与 12 个 overlay](DTBO_OFFLINE_INSPECT.md)，总大小 5,514,578 字节、表头 32 字节、表项 32 字节；旧脚本字节序错误已纠正。debugfs 此时未挂载，暂不把缺少 regulator_summary 解释为硬件故障。新增只读本机内存解码器，用于一次提取 12 个候选 overlay 的表项及 UFS/PMIC 相关属性结构；不写分区、不生成启动包。与具体 Bootloader 选择、PMIC 电气连线和可恢复启动仍须区分。

**12 个 DTBO Overlay 的实测内容（2026-10-17）：** [12 项索引与 umi 唯一候选、共用 UFS 供电属性](DTBO_12_ENTRY_FINDINGS.md) 已核对：索引 0–10 分别对应 alioth、apollo、cas、cmi、dagu、elish、enuma、lmi、munch、psyche、thyme，**索引 11 为 umi**（460,783 字节）。12 项 id/rev/custom 全为 0；每项都含同样 8 个 UFS/PMIC 属性，96 条命中不代表 96 条独立电源轨。旧 DTS 的 `qcom,board-id=<43 0>` 与 DTBO 外层 id 不可混为一谈。尚未还原 phandle 所指目标和 Bootloader 最终选择，硬件门禁保持关闭。

**运行时 UFS 供电 phandle 对照（2026-10-17）：** 为避免继续重复 DTBO 静态扫描，新建[只读的旧系统合成 FDT UFS Host/PHY→regulator 解析器](MERGED_FDT_UFS_LINKS.md)，仅从 Root /sys/firmware/fdt 内存分析中输出已筛选的根模型、board-id 和供电 phandle→目标旧 regulator 关系。是否可在这台机访问 /sys/firmware/fdt 尚待本地执行；不允许将旧系统供电图自动视为主线 6.12 的电气验证。

**P1m 实测 UFS 供电草案（2026-10-17）：** 已读取 umi 真机运行时合成 FDT，8/8 条 UFS 供电 phandle 均存在，其中 7 条直接指向已知 PM8150/PM8150A regulator；`vdd-hba` 的 0x76 已解析到某节点，锁定厂商源码将该旧接口映射到 `ufs_phy_gdsc`。固定主线 6.12 则使用 GCC UFS_PHY_GDSC power-domain。详见 [P1m 运行 FDT→主线 DTS 映射](P1M_RUNTIME_UFS_DTS.md)。新增离线-only P1m DTS 连接 5 个主线标准 UFS/PHY supply 到 P1c 的 disabled regulator 输出，实际 cpp/dtc/fdtget 检查在 CI 中执行。两个额外厂商 UFS 电流/时序投票仍未迁移，六组 PM8150 parent 未核实，所有 UFS/USB 状态继续 disabled；**不能启动或刷机**。

**一次性启动前取证（2026-10-17）：** [Root 集中式采集 + 本地 Boot/Recovery/DTBO 只读备份](ONE_SHOT_PREFLIGHT.md) 已准备，避免重复 P1a~P1m 已采集的 DTBO 和 UFS phandle。一次用户命令获取分区大小、Kernel config/pstore/boot security 等可读资料，并把原始镜像仅存到电脑私有目录、SHA-256 校验；不能自动证明恢复可启动或 Linux 6.12 已可安全刷入。任何研究门禁不变。

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
