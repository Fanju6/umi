# P1m · umi 实机合成 FDT → Linux 6.12 UFS 供电草案

**2026-10-17。真实已启动 umi 的合成 FDT Root 只读报告已核对。** 此阶段从已确认的旧系统供电关系生成一个**仅用于离线 dtc 验证的 6.12 DTS 草案**，不启动设备、不启用任何硬件、不生成 boot.img 或可刷写镜像。

## 真实设备树已经确定的八个供电 phandle

运行时根节点：Qualcomm Technologies, Inc. xiaomi umi；compatible=qcom,kona-mtp/qcom,kona/qcom,mtp；qcom,board-id=<43 0>。不同于之前只有静态源码候选，现在 8 个 UFS Host/PHY phandle **全都在实机合成 FDT 中存在**：

| 旧 DTS 消费属性 | 运行 phandle | 运行 FDT provider / 源码对应 | 6.12 草案 |
|---|---|---|---|
| vdda-phy-supply | 0x7f | PM8150 L5 | &umi_p1c_l5 |
| vdda-pll-supply | 0x80 | PM8150 L9 | &umi_p1c_l9 |
| vcc-supply | 0x2d4 | PM8150 L17 | &umi_p1c_l17 |
| vccq-supply | 0x2cf | PM8150 L6 | &umi_p1c_l6 |
| vccq2-supply | 0xac | PM8150 S4 | &umi_p1c_s4 |
| qcom,vddp-ref-clk-supply | 0x2cf | PM8150 L6 | **厂商私有投票，未移植** |
| qcom,vccq-parent-supply | 0xae | PM8150A S8 | **厂商私有投票，未移植** |
| vdd-hba-supply | 0x76 | phandle 在实机存在，未被旧探针分类；锁定 vendor DTS 引用 ufs_phy_gdsc | **不复制旧 regulator 接口** |

注意：从实机运行状态能证明 PMIC 轨道和旧系统 Provider 的对应；运行时的 phandle 数字只是当次 FDT 内部的索引，不能硬编码到 6.12。

## GDSC：第八个引用不是 PMIC 稳压器缺失

锁定厂商 4.19:
- kona.dtsi 定义 ufs_phy_gdsc，reg=0x177004，compatible=qcom,gdsc，regulator-name=ufs_phy_gdsc。
- xiaomi-sm8250-common.dtsi 的 UFS Host 通过 vdd-hba-supply=< &ufs_phy_gdsc > 消费。
- 本轮运行 FDT 的该 phandle 0x76 被证实存在，但白名单解析器未导出 Provider 的 GDSC 节点名称；**严格说这一步没有从运行 FDT 直接证明 0x76 的具体节点就是 ufs_phy_gdsc**。

固定主线 v6.12 sm8250.dtsi 中 ufshc@1d84000 与 phy@1d87000 已声明 power-domains=< &gcc UFS_PHY_GDSC >，因此新 DTS **不应照搬旧 vendor GDSC-regulator 的 vdd-hba-supply 属性**。从旧 GDSC regulator API 迁移到 6.12 genpd 并不自动保证旧时序/投票完全等效。

## 具体代码进展

新增 research/mainline/sm8250-xiaomi-umi-p1m.dts：

1. 继承 P1c 已存在的 PM8150 RPMh provider 草案；该 provider **status=disabled**，其输出子节点仍为空。
2. 在 **status=disabled** 的 UFS Host/PHY 上指定上表五个 Linux 主线标准 supply phandle，标签来自 P1c 研究 DTS，并非从旧版数字拷贝。
3. 两个厂商私有 UFS 额外投票尚未映射。不能仅因 6.12 qcom-ufs PHY/ref clocks 存在而断言电气等价。
4. 不设置任何 regulator-min/max-microvolt、input parent-supply、initial mode、always-on 或 boot-on；这需要独立真实电气验证。
5. 只通过 GitHub CI 的固定 Linux 6.12 cpp/dtc/fdtget 验证离线 DTB 节点引用及六个相关硬件状态均为 disabled。

为避免误用，此草案不添加到生产 Makefile，也不生成可启动镜像。主线 UFS 更可能通过 power-domains、PHY、clock、ICC 和 regulator 框架标准机制启动，但实际上仍需要验证 UFS VCCQ parent 负载管理、PHY REF rail、PMIC 六组真实 input parent、恢复路径/早期日志等重要阻塞。

## 来源

- 用户 Root 只读报告 umi-merged-fdt-ufs.json（仅记录筛选的硬件元数据，原始完整 FDT 未提交）
- 厂商 4.19 固定 SHA：71b13e62f057a649b77fe4062feb73ee72ad609c；kona.dtsi、xiaomi-sm8250-common.dtsi
- 主线 6.12 固定 SHA：adc218676eef25575469234709c2d87185ca223a；sm8250.dtsi、sm8250-xiaomi-elish-common.dtsi 仅作主线接口验证
- PR #8 开放，稳定 main 不改

safe_to_attempt_mainline_boot=false；safe_to_flash=false。
