# Root 一次性硬件调查：umi Linux 4.19

用户已授权 Root。目标是比 P1a～P1l 的细碎非 Root 审计更直接地采集硬件证据。

## 采集项目

本轮一次运行 scripts/mainline_root_hardware_survey.py，先以普通 ADB 核对 umi 身份，再通过 adb shell su -c sh 进行明确的只读采集：

- 旧系统 9 条 PM8150/PM8150A 实体供电候选的 sysfs 状态、电压和使用计数。
- 如果 debugfs 已挂载且 regulator_summary 可读，记录最多 50 条 PM8150 相关的过滤摘要。不调用 mount。
- 读取当前运行设备树的 qcom,resource-name 字段，仅筛出旧版九个 RPMh 资源 ID；这属于设备树可见声明而不是电气布线测量。
- 读取 /proc/iomem 的资源文本，仅保留与已在旧内核上观察到的 Ramoops 物理区间 [0xB0000000, 0xB0400000) 交叠的区间。
- 读取既有 UFS Host/PHY 设备的 runtime_status 和 control。
- Boot、Recovery、DTBO 三个已有块设备，每个最多读取前 64 字节，只保留解析后的魔数类别和可能的 Boot Header 版本；不保存原始字节，不备份整分区，更不写分区。

此流程在手机侧不写文件、不调整电源、不重启、不挂载 debugfs、不触发内核 panic、不使用 fastboot。不会读取 userdata 分区、Pstore 日志正文或身份证明信息。未筛选的 Root Shell 输出仅在主机进程内解析，不打印、不保存。报告保存在本机指定 JSON 路径，不自动上传。

注：能读取 Root 级元数据只意味着旧版系统的可见状态，不能自动确认 PMIC 物理布线、所有 Firmware 内存 Owner 或主线 Linux 6.12 的可用性。Recovery 分区头可读也不意味着系统能够从失败的新内核恢复。

## PowerShell

~~~powershell
cd C:\Users\fanju\umi-p0b
git pull --ff-only
python -m unittest discover -s tests -p test_mainline_root_survey.py -v
python scripts/mainline_root_hardware_survey.py --probe --output "$env:USERPROFILE\Desktop\umi-root-hardware.json"
~~~

执行时如果 KernelSU、Magisk、APatch 弹出 Root 授权，请允许 ADB Shell。提供过滤后的 JSON 或命令输出，下一步重点解决实际 UFS/PMIC 阻塞；不再反复新增几乎相同的非 Root Probe。

## 未解除的门禁

safe_to_flash=false；safe_to_attempt_mainline_boot=false；未证明恢复分区可启动、已知恢复路径可逆、早期串口/UART 可用、真实主线 UFS 供电时序安全。稳定 main 的 4.19 + KernelSU 不动，研究 PR #8 继续 Open。
