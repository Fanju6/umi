# P1b：umi 4.19 → Linux 6.12 PM8150 电源与 Type-C 核验

> **2026-10-16 | 阶段：固定源码审计、实机白名单只读数据待采集。** 不修改 `main` 上已验证的 Linux 4.19 + KernelSU v3.3.1；不使能 UFS/USB、不刷机、不生成 Boot 镜像。

## 源码事实

固定来源：
- [Linux 6.12 `sm8250.dtsi`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/arch/arm64/boot/dts/qcom/sm8250.dtsi) 和 [`pm8150b.dtsi`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/arch/arm64/boot/dts/qcom/pm8150b.dtsi)
- [umi 4.19 UFS 配置](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom/xiaomi-sm8250-common.dtsi#L43-L73)、[USB 配置](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom/kona-usb.dtsi)、[umi USB-PD](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom/umi-sm8250.dtsi#L723-L746)

| 功能 | 厂商旧版的供电标签 | Linux 6.12 的**待验证物理候选** | 不能提前确定的事项 |
| --- | --- | --- | --- |
| UFS VCC / VCCQ / VCCQ2 | L17 / L6 / S4 | PM8150 LDO17 / LDO6 / SMPS4 | 实际稳压器 phandle、输入来源、限制值 |
| UFS PHY 和 PLL | L5 / L9 | LDO5 / LDO9 | 电压、电流、复位与时序 |
| USB2 HS PHY | L5 / L12 / L2 | LDO5 / LDO12 / LDO2 | PHY 特殊调校和 VBUS |
| USB Type-C / PD | `pm8150b_pdphy` | `pm8150b_typec` | 两者不是兼容驱动实现；需重建角色/连接器绑定 |
| VBUS | `ext_5v_boost` | `pm8150b_vbus` | 不能仅凭名字认定两者接线相同 |
| USB3 | 旧共用 DTS 禁用了 QMP，限制 `high-speed` | 主线有 QMP PHY | 不可因此将 USB3 设为启用 |

Linux v6.12 的 `pm8150b_typec`、`pm8150b_vbus` 在上游 DTS 中已经定义，但是**默认均为 disabled**。某些 SM8250 平板（例如 elish）的 `vreg_l17a_3p0` 等电压设置只是其它板子的参考，不能当作 umi 的安全供电参数。

机器可核查矩阵见 [`config/mainline-p1b-power.json`](../../config/mainline-p1b-power.json)；固定源码校验器见 [`scripts/mainline_p1b_sources.py`](../../scripts/mainline_p1b_sources.py)。即使源码审计通过，也不代表已验证真实电压。

## 2026-10-16 修复：Type-C 子设备名称导致解析中止

首次 umi P1b 实机尝试出现三次 `P1b 采集失败：未知采集路径或属性`。源码检查发现 shell 中的 `/sys/class/typec/port[0-9]*` 也会匹配 `port0-partner`、`port0-cable`、`port0-plug0`，但解析器原本仅允许 `portN`。这属于**代码缺陷的高概率触发点**，未提供原始 ADB 输出，不能断言设备实际是哪一个目录引起。

现在 shell 会跳过并非严格 `port` 加纯数字的 Type-C 子设备，读取 sysfs 属性时只取首行，避免多行值破坏记录边界。解析器仍坚持原白名单，并在失败时报告具体类别/路径或属性名（不记录原始属性值）。新增回归覆盖 Type-C 子设备、名称不合法、多行数据和安全门禁。

重新 `git pull --ff-only` 后运行下面相同命令即可；无需 Root 或清空任何已有报告。若仍失败，请提供**新的错误文本**，它会指明具体类别。首次失败并不证明 UFS、PMIC 或 USB 硬件异常。

## 一次只读实机采集

新 [`scripts/mainline_p1b_probe.py`](../../scripts/mainline_p1b_probe.py) 在普通 ADB Shell 下读取**选择性的** `regulator` 名称、当前电压/状态、Type-C 和 USB role、指定 USB 电源项、UFS 主机节点状态。

不读取 serial、IMEI、MAC、Android ID、电池健康/容量、原始 DTB 或文件内容；不执行 Root、`setprop`、写 sysfs 或更改充电/USB 角色。某些 Android 构建不开放相应 sysfs 项，返回空列表和 `missing` **不是设备故障的证据**。

Windows PowerShell：

```powershell
cd C:\Users\fanju\umi-p0b
git pull --ff-only
python scripts/mainline_p1b_probe.py --output "$env:USERPROFILE\Desktop\umi-p1b-power.json"
```

输出存储在本地桌面，先人工检查再分享。工具不会自动上传设备信息到 GitHub。

## 下一个验收点

先根据这台 umi 的真实 sysfs 读数核对 PMIC 和 UFS/USB 的依赖，区分“运行时电压”与“可以在 DTS 配置的安全范围”；再针对可验证的设备加入板级电源定义和低风险 DT schema 检查。USB PD、charging HAL、备用启动日志及恢复能力尚未验收，六个控制器/PHY 维持 `disabled`。

**状态：`P1B_STATIC_MAPPING`、`P1B_DEVICE_POWER_PENDING`、`P1B_NO_HARDWARE_ENABLED`、`SAFE_TO_FLASH_FALSE`。**

## 2026-10-16：首份实机 P1b 报告与稳压器采集修复

实机报告 `umi-p1b-power.json` 已核对：`device=umi`，`writes_performed=false`；Type-C 端口 `port0` 为 `data_role="host [device]"`（当前 Device）、`power_role="source [sink]"`（当前 Sink），`port_type="[dual] source sink"`；USB 电源节点 `usb` 为 `type=USB_PD`、`online=1`、`voltage_max=5000000`、`current_max=1550000`。**后两个为电源框架报告的上限属性，并不是万用表读数、实时充电电压/电流或已确认的 PD 协商 PDO**。另 `pc_port` 为 offline，`main` 节点的 4.4V 上限不应作为 USB VBUS。

初始报告 `regulator={}`、`usb_role={}`、`1d84000.ufshc/status=missing`，**均不能据此认定硬件不存在或关闭**。

**已复核的真正采集器 bug：** [umi 锁定 Linux 4.19 的 `drivers/regulator/core.c` 第 4866 行](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/drivers/regulator/core.c#L4866) 实际使用 `dev_set_name(&rdev->dev, "regulator.%lu", ...)`；[Linux v6.12](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/regulator/core.c#L5734) 亦同。最初 P1b 采集脚本只扫描 `regulator[0-9]*`，解析器也只接受 `regulator7`，**漏掉标准的 `regulator.7`**。现已补上带点号的目录模式及严格解析（兼容旧模式），新增针对 `regulator.7` 和异常子目录的回归。此前 Type-C 子设备模式也已收紧。

因此 P1b 的稳压器实机验收仍须在更新后的脚本上**再执行一次**；无需重做 P0c、无需 Root 或修改设备。

## 2026-10-16：第二份实机报告：七条实体 PM8150 供电轨均已观察

最新由普通 ADB Shell 生成的 `umi-p1b-power(1).json` 已人工核对，`regulator=56`、`typec=1`、`usb_supply=3`、`ufs=1`。**仓库不保存整份用户原始 JSON**，只保存 [脱敏的七轨状态快照](../../config/mainline-p1b-observed.json)（无手机唯一 ID、无原始设备文件、无动态 regulator.N 编号）；与八条旧 DTS 供电引用的关系可由 [离线检查器](../../scripts/mainline_p1b_observations.py) 验证。

| 实机稳压器 | 旧 4.19 用途 | sysfs 当前 `microvolts` | sysfs `min/max` | 运行状态 |
| --- | --- | ---: | --- | --- |
| `pm8150_l17` | UFS VCC | 2,504,000 μV | 2,496,000–3,008,000 μV | enabled |
| `pm8150_l6` | UFS VCCQ | 1,200,000 μV | 1,200,000–1,200,000 μV | enabled |
| `pm8150_s4` | UFS VCCQ2 | 1,800,000 μV | 1,800,000–1,920,000 μV | enabled |
| `pm8150_l5` | UFS PHY、USB2 PHY | 880,000 μV | 880,000–880,000 μV | enabled |
| `pm8150_l9` | UFS PLL | 1,200,000 μV | 1,200,000–1,200,000 μV | enabled |
| `pm8150_l12` | USB2 PHY | 1,800,000 μV | 1,800,000–1,800,000 μV | enabled |
| `pm8150_l2` | USB2 PHY | 3,072,000 μV | 3,072,000–3,072,000 μV | enabled |

**证据解读**：上述七条是运行中 **Linux 4.19 regulator sysfs** 的值，八条用途来自固定 SHA 的厂商 DTS。不是物理电压测量，也不是可以将这些 min/max 原样写入 Linux v6.12 `regulator-min/max-microvolt` 的证明。特别是 `pm8150_l17` 此刻 2.504V，而旧版 sysfs 报告最大 3.008V，不能自行取最大值。

还观察到 `pm8150_l5_ao`、`pm8150_l12_ao` 等虚拟/投票变体；它们不等于可再创建一个独立物理 LDO。带 `_level` 名称的 QCOM 电源投票有时报告 `microvolts=16/64/256` 等非普通电压量，不能换算成伏特后用于引脚供电。

`ufs_card_gdsc`、`ufs_phy_gdsc` 的 regulator 包装节点都报告为 `disabled`，且没有 `microvolts` 属性；这和已在正常系统下工作的 UFS 控制器并不矛盾。单独的 GDSC wrapper 状态不能判定硬件/存储是否工作，需要分别核对 power-domain runtime 状态和实际 UFS 驱动/块设备。Type-C 保持当时的 device/sink，USB `online=1` / `type=USB_PD`，旧版 USB 框架报告 `voltage_max=5V` / `current_max=1.55A`，这些上限不是独立的电压、电流实时测量，也不能当作已协商的 PD PDO。

### 自动复核与门禁

```powershell
python scripts/mainline_p1b_observations.py
# 可选：仅在本地将归纳后的 7 轨状态与原始报告一一比对；不上传或复制原 JSON：
python scripts/mainline_p1b_observations.py --report "$env:USERPROFILE\Desktop\umi-p1b-power.json"
```

校验器核对 **七个不同实体轨、八条旧版供电引用、当前状态及快照约束**，拒绝异常、缺失、虚拟变体混入，也始终保留 `safe_to_flash=false`、`safe_board_voltage_ranges_verified=false` 与 `rpmh_binding_verified=false`。若第二条命令使用的文件是旧的零稳压器报告，会正确拒绝；需要选中最新的 `umi-p1b-power(1).json` 路径。这不是可启动电源树或已启用 Linux 6.12 UFS。

### P1c 前真正尚缺的内容

- UFS：PM8150/LDO/SMPS 在主线 `qcom-rpmh-regulator` 的节点地址、SMD/RPMh ID、父供电关系、IOMMU/power-domain/clock、请求负载与启用顺序，不能只凭名称创建 `vreg_l17a` 之类 phandle。
- USB：PM8150B Type-C PD/角色和 ext_5v_boost 的硬件拓扑、连接器 graph、VBUS source/sink 操作权限与 USB2 PHY 旧版调校。旧内核的 USB_PD 只能证明旧驱动当前工作。
- 恢复门禁：仍缺可靠的可回滚启动日志通道及统一 Boot/DTBO 分析；P1a 的六个 UFS/USB/PHY 节点继续保持 `disabled`，不能生成可刷写内核镜像。

**阶段更新：`P1B_LEGACY_7_RAILS_OBSERVED`，`P1B_8_SUPPLY_LINKS_ACCOUNTED`，`P1B_VOLTAGE_FOR_MAINLINE_UNVERIFIED`，`NO_612_BOOT`，`SAFE_TO_FLASH_FALSE`。**
