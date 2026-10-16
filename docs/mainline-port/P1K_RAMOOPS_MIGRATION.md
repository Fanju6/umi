# P1k · umi 旧版 Ramoops 运行时参数与主线 6.12 迁移门禁

**2026-10-16。只读元数据与静态研究；没有尝试高版本启动，没有进行 Root、写内存或刷机。**

## P1j 实机新证据

用户已在实际运行的 umi 4.19 上执行非 Root 的 P1j 探针，提供脱敏输出并在本地完成完整 JSON 校验：

| sysfs 参数 | 真机读取值 | 对照 |
| --- | ---: | --- |
| mem_address | 2952790016 | 0xB0000000 |
| mem_size | 4194304 | 4 MiB |
| console_size | 2097152 | 2 MiB |
| pmsg_size | 2097152 | 2 MiB |

测试者回报 all_four_parameters_readable=true、parameter_values_match_vendor_candidate=true，且用户本地 --report 审计结果 local_report_verified=true、values_match_locked_vendor_source=true。**这是旧版 4.19 运行时参数吻合证据，不是该物理内存所有权完备性证明。**

仓库只保存用户分享的摘要数值与证据等级，未获得或保存用户电脑上的完整脱敏 JSON 文件，未读取 Pstore 日志正文、原始设备树、裸 RAM 或个人信息。

## 内存区间与信息边界

旧版 Ramoops 实测参数指向的半开范围为 **[0xB0000000, 0xB0400000)**。P0c 的 22 个固定保留内存区域没有与它重叠，且已观察到显示运行时转储区从 **0xB0400000** 开始，首尾相接。但 12 个动态内存池没有实际基址，其他固件和 bootloader RAM owner 未完整审计。

因此，运行时四参数与旧源码完全匹配；Linux 6.12 可安全复用同一区域仍为 false。未证明崩溃跨重启保留，也未验证非 A/B 恢复路径。所有刷机和试启动门禁继续关闭。

## Linux 6.12 的接入差异

锁定主线 6.12 的 fs/pstore/ram.c：设备树分支使用 platform_get_resource(..., IORESOURCE_MEM, 0) 找到实际资源，再读取 record-size / console-size / pmsg-size / ftrace-size 等属性。ramoops.yaml 中 compatible 与 reg，以及必要的记录缓冲配置，属于设备树绑定约束。

旧 BSP 专用的 ramoops_memreserve=4M 处理及硬编码地址不在所锁定的主线实现中。**当前绝不把 0xB0000000 直接作为可用 ramoops DTS 节点加入研究设备树**；即使后续在单独环境完成 DT 模型，也不等于主线可启动。

## P1k 工程变更

- 新增 config/mainline-p1k-ramoops-migration-evidence.json，明确用户分享的真机元数据、出处与未验证风险。
- 新增 scripts/mainline_p1k_ramoops_bridge_audit.py，离线校验 P0c、P1j 与 P1k 数据；可选仅在本地读取此前生成的脱敏 P1j JSON；对凭空打开刷机/主线复用权限的修改直接拒绝。
- 修正 scripts/mainline_p1j_ramoops_memory_audit.py：只有提供并成功校验本地 --report 且四项完全吻合时，live_module_parameter_values_verified 才是 true；不提供报告时仍为 false。无论此字段如何，物理内存安全和启动门禁都保持 false。
- 新增 P1k 专项单测与固定 Linux 6.12 源码的 GitHub CI；不运行设备探针。

## 本地纯离线复核（PowerShell）

~~~powershell
cd C:\Users\fanju\umi-p0b
git pull --ff-only
python scripts/mainline_p1k_ramoops_bridge_audit.py
python -m unittest discover -s tests -p test_mainline_p1k.py -v
python -m unittest discover -s tests -p test_mainline_p1j.py -v
~~~

现有 P1j 脱敏 JSON 已在本机，可再核验一次：

~~~powershell
python scripts/mainline_p1j_ramoops_memory_audit.py --report "$env:USERPROFILE\Desktop\umi-p1j-ramoops-params.json"
python scripts/mainline_p1k_ramoops_bridge_audit.py --report "$env:USERPROFILE\Desktop\umi-p1j-ramoops-params.json"
~~~

第一条在本地报告完全吻合时应显示 live_module_parameter_values_verified=true；第二条显示 local_report_verified=true 与 runtime_metadata_match=true，complete_physical_ownership_verified=false、safe_to_flash=false 不改变。

## 下一步重心

Pstore/Ramoops 旧系统来源与参数的关键证据基本齐备。后续优先回到 **P1e/P1f 尚未闭合的 UFS/PMIC parent、供电及恢复能力**：这些比反复检查文件名更直接阻塞 Linux 6.12 可恢复启动。任何 Linux 6.12 启动、供电控制器使能、刷机权限仍需要另外的独立验证。

资料：[P1j](P1J_RAMOOPS_MEMORY.md)、[P0c](P0C_FULL_MEMORY_AND_DTC.md)、[Torvalds 6.12 Ramoops 驱动](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/fs/pstore/ram.c)、[Ramoops 绑定](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/Documentation/devicetree/bindings/reserved-memory/ramoops.yaml)。
