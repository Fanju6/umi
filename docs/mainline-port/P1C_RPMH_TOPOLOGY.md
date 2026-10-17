# P1c：umi 的 Linux 6.12 RPMh regulator 输入供电拓扑（研究）

> **2026-10-16 · 仅离线建模 / 不可引导 / 不可刷写。** P1b 已观察到 56 条 regulator 记录，七条 UFS/USB2 PHY 目标稳压器均 enabled。P1c 建立了它们与固定主线 regulator binding 的**输入属性组**之间的关系；尚未确定实际父供电节点或 PMIC RPMh ID。

## 固定证据与关键发现

- [主线 v6.12 `qcom,rpmh-regulator.yaml`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/Documentation/devicetree/bindings/regulator/qcom,rpmh-regulator.yaml)：PM8150 可使用 `qcom,pm8150-rpmh-regulators`，其下分别创建 `ldoN` / `smpsN` 节点；PMIC provider 位于 RPMh RSC 设备下，要求 `compatible` 与 `qcom,pmic-id`。
- 主线 SM8250 SoC 的 `apps_rsc: rsc@18200000` 已含 RPMh TCS、clock 与 power-domain。**SoC 控制器存在不代表 umi 的 PMIC 输出已经有供应商安全配置**。
- [elish 的 RPMh DTS](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/arch/arm64/boot/dts/qcom/sm8250-xiaomi-elish-common.dtsi#L164-L290) 用 `qcom,pmic-id="a"` 对应其主 PM8150、输入电源来自 VPH_PWR、其它 SMPS 和 PM8150L BOB。**这是其它硬件的案例，不是 umi 输入电路、PMIC ID 或具体电压的实测证明**。
- 原 umi 4.19 DTS 的八条供电引用，已通过 P1b 实机 7 轨数据对应；虚拟 `_ao`/`_so` 和 `_level` 电源投票未混入实体供电轨。

## 七条输出、六组主线供电输入属性

| 输出轨 | Linux 6.12 provider 子节点 | 主线 binding 规定的父供电属性名称 | umi 4.19 报告当前电压 |
| --- | --- | --- | --- |
| PM8150 S4 | `smps4` | `vdd-s4-supply` | 1.800V |
| PM8150 L2 | `ldo2` | `vdd-l2-l10-supply` | 3.072V |
| PM8150 L5 | `ldo5` | `vdd-l3-l4-l5-l18-supply` | 0.880V |
| PM8150 L6 | `ldo6` | `vdd-l6-l9-supply` | 1.200V |
| PM8150 L9 | `ldo9` | `vdd-l6-l9-supply` | 1.200V |
| PM8150 L12 | `ldo12` | `vdd-l7-l12-l14-l15-supply` | 1.800V |
| PM8150 L17 | `ldo17` | `vdd-l13-l16-l17-supply` | 2.504V |

**重要：属性名在 binding 中有明确类型，但其右侧 `<&真实父供电>` 尚未确认。** 不得通过 elish 的父供电 phandle 或 sysfs 的 `min/max_microvolts` 直接构造 umi 上的可启用电源树。UFS/USB PHY 的供电输入依赖关系仍保留在 [P1b 映射](../../config/mainline-p1b-power.json)。

## 研究产物

1. [RPMh 拓扑矩阵](../../config/mainline-p1c-rpmh-topology.json) 将七条实体轨、六个输入供电属性、八条旧版消费引用以及缺失的父供电/电压约束分别建模。电压只附有旧 4.19 **观测值**，未赋主线电压范围。
2. [P1c DTS 骨架](../../research/mainline/sm8250-xiaomi-umi-p1c.dts) 继承 P1a，向 `&apps_rsc` 添加 **`status="disabled"` 的示范性 PM8150 RPMh provider**，有七个空输出节点、**零父供电 phandle、零新电压限制、零 regulator-always-on/boot-on**。写入 `qcom,pmic-id="a"` 只为演示上游 elish 的绑定结构；明确标记 umi 未验证，不能当成可用配置。
3. [P1c 检查器](../../scripts/mainline_p1c_topology.py) 自动检验数据与 P1b 证据一致、主线 binding 的六个输入属性、禁用状态及未应用电压设置。配套 [回归测试](../../tests/test_mainline_p1c.py) 阻止任何过早使能。
4. CI 将使用锁定 Linux v6.12 源码运行 GNU CPP / `dtc`，并回读该 provider 的 `status`；成功仅代表 DTS **可离线编译**，不表示完整 schema、PMIC 探测或主线启动已被验证。

## 下阶段 P1d 阻塞

- 必须从公开 umi BSP 与实际 PMIC/RPMh 接口继续核对主 PMIC `qcom,pmic-id` 真实映射、VPH_PWR/SMPS/BOB 父供电，以及 RPMh 输出轨的输入电源关系；如仍缺则保持 unknown。
- 需核查 UFS PHY 的 `power-domains`、clocks、PHY init、实际 regulator voltage constraints 与是否适合该机 UFS 型号，**不能因为 sysfs 曾报告 enabled 就在主线 DTS 启动 UFS**。
- Type-C `pm8150b_typec`、`pm8150b_vbus` 的连接器/PD 和充电安全操作路径与旧版小米驱动不相同。仍需 UFS/USB 故障日志、恢复环境与启动协议确认。
- 当前 **`safe_to_flash=false`**；Linux 6.12 / GKI 6.12 均未在 umi 上启动/编译为可刷写镜像；KernelSU 4.19 主线不动。
