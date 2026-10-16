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
