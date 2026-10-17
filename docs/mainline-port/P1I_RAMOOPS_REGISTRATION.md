# P1i：umi Pstore 后端注册路径观察（不读取物理地址）

**2026-10-16；safe_to_flash=false、safe_to_attempt_mainline_boot=false。**

## 为什么继续核对注册路径

用户在现有 umi 4.19 系统的非 Root P1g 探针中实测：Pstore 已挂载，能看到 console-ramoops* 和 pmsg-ramoops* 两类文件。P1h 又用用户本地完整脱敏报告完成一致性验证：local_report_verified=true，17 项本地测试通过。

P0c 来自同一 umi 旧系统的 34 节点运行时 reserved-memory 白名单：**22 个固定区 + 12 个动态池，节点名中 0 个明确叫作 ramoops**。这并不证明系统不存在 ramoops。可能存在设备树以外的平台数据/启动参数注册方法、候选设备树节点位于其他位置、权限导致看不到某些节点，或探针搜索范围不足；不能擅自选择其中某个为确定原因。

尤其不能因 console/pmsg 文件存在就任意选择 P0c 的 XBL/UEFI 日志 0x80880000 或其他保留区作为主线 6.12 ramoops。这可能与启动固件、TrustZone 或其他系统组件冲突。

## 当前采用的三个保守观察

新工具 scripts/mainline_p1i_ramoops_probe.py 仅在明确传入 --probe 后，使用普通 ADB Shell，读取如下已知元数据：

1. /sys/bus/platform/devices/ramoops 及 ramoops.* 的目录是否存在（平台设备名候选）；
2. /sys/firmware/devicetree/base/ramoops、ramoops@*，以及 reserved-memory 直下各节点的 compatible 是否包含 ramoops（设备树候选，而不是设备树 reg）；
3. /sys/module/ramoops/parameters 是否有目录（内核模块/内建参数可见性，不读其中的内存地址或大小）。

还会复核 umi、4.19、非 A/B、启动完成和 Pstore 挂载状态；只会输出布尔值。**不读取任何 ram、raw DTB、reserved-memory/reg 二进制、物理地址、pstore 日志正文、cmdline、块设备、IMEI、序列号等，不请求 Root，不执行 reboot、flash、mount、dd，也不上传文件。**

### 本地命令

只读离线，无手机访问：

~~~powershell
cd C:\Users\fanju\umi-p0b
git pull --ff-only
python scripts/mainline_p1i_ramoops_audit.py
python -m unittest discover -s tests -p test_mainline_p1i.py -v
~~~

你可选择再执行一次新的、明确开启的只读探针：

~~~powershell
python scripts/mainline_p1i_ramoops_probe.py --probe --output "$env:USERPROFILE\Desktop\umi-p1i-ramoops.json"
~~~

该探针只输出三项注册候选信号及安全状态，不读取/修改设备内容。在用户得到报告后，可以在本地再运行下面的离线校验，无需重复连接 ADB：

~~~powershell
python scripts/mainline_p1i_ramoops_audit.py --report "$env:USERPROFILE\Desktop\umi-p1i-ramoops.json"
~~~

以上两个阶段分别是**读取设备公开节点是否存在**与**验证已经保存的脱敏 JSON**。如果 platform_device=true、DT_compatible=false，只证明该候选平台注册入口可见、没有在上述 DT 路径找到匹配的 compatible；**不能据此直接断言后端一定由 platform data 注册、也不能推算地址**。如果两项都为 false，也不能据此断言 ramoops 不存在，必须复核探针范围、用户权限、旧内核实现。

## 工程文件

- config/mainline-p1i-ramoops-registration.json：P0c 34 节点中的 ramoops 名称缺口，已确认的 Pstore 类别，以及全部未验证的实际物理区/恢复门禁；
- scripts/mainline_p1i_ramoops_audit.py：离线交叉核对 P0c/P1h 的安全状态、可选本地脱敏 P1i 报告；
- scripts/mainline_p1i_ramoops_probe.py：显式 opt-in、非 Root ADB 标记采集；
- tests/test_mainline_p1i.py：验证真实 P0c 名称缺口、错误设备/A-B 拒绝、禁用原始日志读取和刷机权限；
- .github/workflows/mainline-p1i-ramoops.yml：只执行离线验收与 P1h/P1g 回归。

## 不变的严格门禁

- 旧系统存在 Pstore 文件：已证明；主线 6.12 在 umi 上可稳定使用同一区域：**未证明**。
- P0c 内没有叫 ramoops 的保留节点：已证明；实际物理 RAM 里不存在其他注册区域：**未证明**。
- 崩溃数据能跨重启留存：**未证明**；Recovery、已知可用 4.19 恢复、UART earlycon：**未证明**。
- 六组 PMIC parent、UFS 私有 regulator 投票、电源时序未完成，因此 Linux 6.12 试启动与刷机：**仍禁止**。

后续只能在得到实际脱敏的注册路径证据后，再研究**受限的只读 DT 地址属性**是否可用于与 P0c 区间做离线冲突检查；不能从路径存在性跳跃到物理地址或生成可用 DTS。

见 [P1g](P1G_RECOVERY_LOG_GATES.md)、[P1h](P1H_PSTORE_EVIDENCE.md)、[P0c](P0C_FULL_MEMORY_AND_DTC.md)。
