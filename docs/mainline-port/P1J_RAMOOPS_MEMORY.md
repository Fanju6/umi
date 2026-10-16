# P1j：umi 4.19 ramoops 源码级内存区间与 P0c 对照

**2026-10-16。公开源码 + 既有设备只读证据。尚未证明实际运行时 ramoops 地址；不会刷机、开机测试、Root 提权或读取原始物理内存。**

## 一、P1i 实机结果与新发现

P1i 已经完成真实非 Root ADB 检查、16 项本地测试及本地 JSON 审计。用户确认：

- pstore_mounted = true
- ramoops_platform_device_name_observed = true
- ramoops_dt_compatible_candidate_observed = false
- ramoops_module_parameters_dir_present = true
- local_report_verified = true

该结果符合**旧版内核通过设备树以外的平台注册路径创建 ramoops**这一候选解释；尚不构成由此机制注册的运行时物理地址证明。此前 P0c 34 个 reserved-memory 节点中无明确名为 ramoops 的节点，也不能用来否定旧内核的其他内存保留路径。

在固定版本的 LineageOS 4.19 源码（71b13e62f057a649b77fe4062feb73ee72ad609c）中，进一步直接核查到：

- arch/arm64/configs/vendor/xiaomi/sm8250-common.config 含 CONFIG_CMDLINE="cgroup_disable=pressure ramoops_memreserve=4M"。
- fs/pstore/ram.c 的 ramoops_memreserve 使用 early_param 接收该配置，memparse 对齐后把 ramoops_data.mem_address 设为 0xB0000000，并将大小设置为参数长度；分别把 console_size 和 pmsg_size 设置为总长度一半。
- 同一处理器调用 memblock_reserve(ramoops_data.mem_address, ramoops_data.mem_size)；core_initcall(msm_register_ramoops_device) 以 platform_device_register(&ramoops_dev) 创建名为 ramoops 的平台设备。
- 旧驱动完成 probe 后还会将平台数据回填到 /sys/module/ramoops/parameters 对应的内核参数变量。

**固定 CONFIG_CMDLINE 的字面配置并不独立证明正在运行的设备实际采用了这条启动参数。** 真实生效值需要单独读取旧内核导出的 sysfs 数字元数据。内核和 bootloader 最终合成 cmdline 的方式尚未审核，此阶段不读取 /proc/cmdline。

## 二、源码候选物理区域：与 P0c 的半开区间核验

仅在 ramoops_memreserve=4M 生效时，旧源码按固定逻辑给出如下**候选布局**：

| 区域 | 半开范围（结束地址不包含） | 大小 |
| --- | --- | --- |
| Ramoops 整体候选 | [0xB0000000, 0xB0400000) | 4 MiB |
| Console 候选缓冲 | 总量一半（具体内部 offset 仍依赖旧实现） | 2 MiB |
| Pmsg 候选缓冲 | 总量一半（具体内部 offset 仍依赖旧实现） | 2 MiB |
| P0c Display runtime dump（实机固定区） | [0xB0400000, 0xB1400000) | 16 MiB |

依据 P0c 已保存的 22 个固定区间，对 [0xB0000000, 0xB0400000) 做半开区间数学计算，**0 个固定区间重叠**，并与 P0c 显示 dump 区在 0xB0400000 恰好相邻。该结论仅限已经纳入 P0c 的 22 个固定 DT 节点。其余 12 个动态池尚无实际物理基址，其他 bootloader、固件以及不在 DT 清单中的 RAM owner 也没有完全列举。因此零重叠**不是安全复用许可**。

锁定 Torvalds 6.12（adc218676eef25575469234709c2d87185ca223a）的 fs/pstore/ram.c 没有上述 vendor 专用 ramoops_memreserve early_param 与固定 0xB0000000 赋值。主线若需要适配，必须使用已核验的 reserved-memory、正确的 binding、后端/恢复语义与完整内存所有权证明；本阶段**不加 ramoops DT 节点，不复制硬编码，不生成启动镜像**。

## 三、工具与安全门禁

- config/mainline-p1j-ramoops-memory.json：保存候选 0xB0000000 / 4 MiB 的确切源码来源、与 P0c 的半开区间关系、所有“未经运行时验证”状态。
- scripts/mainline_p1j_ramoops_memory_audit.py：默认离线检查 P0c 22 固定/12 动态与 P1i 证据，发现候选与任何固定保留区重叠时立即失败；CI 用固定 SHA 的 vendor ram.c、sm8250-common.config、主线 6.12 ram.c 验证源码标记。
- scripts/mainline_p1j_ramoops_params_probe.py：必须明确传入 --probe，才以普通 adb shell 读取 /sys/module/ramoops/parameters/{mem_address,mem_size,console_size,pmsg_size} 的**只读数字元数据**。不读取 Pstore 日志正文、/proc/cmdline、/proc/iomem、原始 DT、原始 RAM 或分区，不请求 Root、不修改文件、不重启。参数若权限限制，仅标记 null / unreadable，绝不跳过权限限制。
- tests/test_mainline_p1j.py：模拟参数可读/不可读、十进制/十六进制、错误设备、误填内存、虚假启动许可等；CI 完全不连接手机。
- .github/workflows/mainline-p1j-ramoops-memory.yml：专项固定 SHA 源码审计 + P1i / P1h 回归。

## 四、本地核验操作（PowerShell）

仅静态，不连接设备：

~~~powershell
cd C:\Users\fanju\umi-p0b
git pull --ff-only
python scripts/mainline_p1j_ramoops_memory_audit.py
python -m unittest discover -s tests -p test_mainline_p1j.py -v
~~~

如愿意，可选择读取**非敏感硬件地址/大小元数据**，普通 ADB Shell 权限不足时不会提权：

~~~powershell
python scripts/mainline_p1j_ramoops_params_probe.py --probe --output "$env:USERPROFILE\Desktop\umi-p1j-ramoops-params.json"
~~~

该命令只读取 sysfs 的四个数值参数，不读取物理内存本身。如果结果显示 unreadable/null，属权限不足的合理结果，并不否定源码证据。接着可离线验证，不重新访问手机：

~~~powershell
python scripts/mainline_p1j_ramoops_memory_audit.py --report "$env:USERPROFILE\Desktop\umi-p1j-ramoops-params.json"
~~~

即使四个数字都吻合，也只能称为**当前旧内核导出参数与锁定源码相符**；依然不能保证这块内存适合未来 Linux 6.12，不能说崩溃后能可靠恢复。

## 五、后续需要的真正证据

- 如果 sysfs 四参数可读且吻合，下一步复核实际 pstore memory owner、ramoops 是否跨正常重启保留日志（不通过故意 crash/panic 验证），以及不可忽略的 12 个动态池/其他固件 RAM 区间。
- 如果参数不可读，保持地址候选不升级为实测，不尝试 su 或未经许可的提升权限。可以继续审核锁定 BSP 的启动参数注入路径和 memblock_reserve 顺序。
- 仍需独立确认非 A/B Recovery 与可逆恢复路径、UFS/PMIC 六组真实 parent、电气时序以及设备本身的 Linux 6.12 早期日志；所有刷机/启动安全门禁保持 false。

源：[旧 BSP ramoops](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/fs/pstore/ram.c)；
[旧 sm8250-common.config](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/configs/vendor/xiaomi/sm8250-common.config)；
[主线 6.12 ramoops](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/fs/pstore/ram.c)；
[已完成的 P1i](P1I_RAMOOPS_REGISTRATION.md)。
