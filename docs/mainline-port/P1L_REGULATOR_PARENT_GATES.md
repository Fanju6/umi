# P1l · umi RPMh 输入供电：DTS 合法性 ≠ 板级上电就绪

**2026-10-16。Linux 4.19/6.12 固定公开源码与 P1d/e/f 证据交叉核对；无手机操作、无电压写入、无 DTS 使能、无刷机。**

## 前置结果

- P1k 旧内核 Ramoops 测试者现场已报告 14 项通过；P1j 同一现场用本地脱敏 JSON 得到 live_module_parameter_values_verified=true。P1k 最后一个本地 --report 命令的输出还未见到，因此不能在此声称该命令已经通过。
- Ramoops 4.19 源码/运行时参数核对基本完成；接下来影响 Linux 6.12 UFS 的重点是 PMIC parent 实际布线、UFS 私有电源投票及恢复能力。
- P1d 固定源码与旧 4.19 实机分别支撑七个 RPMh regulator 输出身份和 4.19 时刻的电压，但不构成 Linux 6.12 可用电压的设置依据。
- P1e 有六组主 PM8150 parent supply phandle 为 null；P1f 两条 Vendor UFS 供电投票仍无主线等价性证明。

## 主线 Linux 6.12 静态源码新确认

根据固定上游 adc218676eef25575469234709c2d87185ca223a：

1. Documentation/devicetree/bindings/regulator/qcom,rpmh-regulator.yaml 的**顶层 required** 为 compatible 与 qcom,pmic-id；PM8150 六组输入供电属性位于条件 schema 的允许属性集合，并非所有六项在该 binding 中被强制 required。
2. drivers/regulator/qcom-rpmh-regulator.c 的 PM8150 regulator 静态数据表，为每个 SMPS/LDO 输出定义 supply_name；rpmh_regulator_init_vreg 将其写入 regulator_desc.supply_name，并以 cmd_db_read_addr() 解析 RPMh 资源名。
3. 因此 DTS 未填写上游供电 phandle 时，某些静态 binding/编译检查可能仍通过。这**不能证明 PMIC 的电气供电、上电次序、负载投票、动态频率变更或真实 UFS 数据可靠性**。同样不能从旧版 regulator 输出电压反推输入端 VPH_PWR/电池实际接线。

结合 P1d 的七个物理输出轨，在 Linux 6.12 的供电输入名称里拆分为以下六组：

| 输入属性 | 旧版 regulator 输出 | 主线 6.12 输出名 | umi parent |
| --- | --- | --- | --- |
| vdd-s4-supply | pm8150_s4 | smps4 | 未知 |
| vdd-l2-l10-supply | pm8150_l2 | ldo2 | 未知 |
| vdd-l3-l4-l5-l18-supply | pm8150_l5 | ldo5 | 未知 |
| vdd-l6-l9-supply | pm8150_l6、pm8150_l9 | ldo6、ldo9 | 未知 |
| vdd-l7-l12-l14-l15-supply | pm8150_l12 | ldo12 | 未知 |
| vdd-l13-l16-l17-supply | pm8150_l17 | ldo17 | 未知 |

其中两组别额外旧 Vendor 供电仍不能映射：qcom,vddp-ref-clk-supply → pm8150_l6（实际 enable/disable 相关）和 qcom,vccq-parent-supply → pm8150a_s8（set_load 等条件投票、WLAN/BT 共用参考）。具体行为见 [P1f](P1F_UFS_LIFECYCLE.md)。

## 工程实现

- config/mainline-p1l-regulator-parent-gates.json：以数据结构永久区分“binding 可接受的输入属性”和“真实 PCB 已验证 parent”，七条轨归入六组，两个额外投票保持 null。
- scripts/mainline_p1l_regulator_parent_audit.py：纯离线对照 P1d/P1e/P1f、P1a/P1c 的全部关键禁用节点；可选固定源码交叉核验，对无依据增加 phandle 或开放 UFS/PMIC 的修改 fail-closed。
- tests/test_mainline_p1l.py：负向测试覆盖错误地把 schema 允许项视为真实硬件证据、虚假供电接线、误用 voltage、错误归组、旧私有 vote 直接替换、UFS/PMIC 误启用。
- .github/workflows/mainline-p1l-regulator-parent.yml：独立 CI 从固定 Linux 6.12 SHA 获取 RPMh regulator 驱动及 binding，交叉核对六组 supply_name 和 required 属性，不连接手机。

## PowerShell 离线回归

~~~powershell
cd C:\Users\fanju\umi-p0b
git pull --ff-only
python scripts/mainline_p1l_regulator_parent_audit.py
python -m unittest discover -s tests -p test_mainline_p1l.py -v
~~~

本轮无需新的真机命令。仍需实际 PCB/BOM/旧内核 DTBO 合成证据验证 parent 供电、UFS 电源时序；在缺少证明前不生成高版本可刷写 boot.img，也不修改研究 DTS 里面所有显式 disabled 的节点。必须同时验证 umi 非 A/B 的可靠恢复路径和早期日志采集。

**安全门禁：safe_to_attempt_mainline_boot=false；safe_to_flash=false。**

固定参考：
- https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/Documentation/devicetree/bindings/regulator/qcom,rpmh-regulator.yaml
- https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/regulator/qcom-rpmh-regulator.c
- [P1d](P1D_VRM_EVIDENCE.md) · [P1e](P1E_UFS_PARENT_AUDIT.md) · [P1f](P1F_UFS_LIFECYCLE.md) · [P1k](P1K_RAMOOPS_MIGRATION.md)
