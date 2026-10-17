# P1e · umi UFS 父供电与 RPMh S8/BOB 源码审计

**阶段：2026-10-16，固定版本公开源码 / Linux 4.19 已有实机证据。不可启动、不可刷写；safe_to_flash=false。**

## 新发现：旧 PM8150A 的两条 RPMh 资源

固定 LineageOS 4.19 Kona VRM 描述中，pm8150a_s8 属于 smpc8，pm8150a_bob 属于 bobc1。固定主线 Linux 6.12 的 qcom-rpmh-regulator.c 在 PM8150L 设备类型下为 smps8 使用 smp%s8 模板、bob 使用 bob%s1 模板；qcom,rpmh-regulator.yaml 允许 qcom,pm8150l-rpmh-regulators。资源后缀均为 c，构成候选 PMIC ID 的公开源码证据，但不能证明高版本主线对 umi 的 PMIC 真实探测，也不能把厂商 pm8150a 与主线 pm8150l 的称呼等同于完整的板级电路原理图。

**与此不同，原 P1d 的七轨 suffix a 属于主 PM8150，不能混淆。**

## VPH_PWR 和六组 PM8150 输入父供电

umi-sm8250.dtsi 出现的 vph_pwr@83 是 PMIC ADC 测量通道，label 为 vph_pwr；它不能独立证明存在适合作为 RPMh 输入的主线 regulator-fixed 节点或其电压。elish 上定义的 3.7V VPH_PWR 和 SMPS/BOB 连接是其它设备的配置，绝不能直接照搬。

主线已经确定以下属性名称，但 umi PCB 具体上游连线依然未知：

| PM8150 输入属性 | umi 父供电 phandle |
| --- | --- |
| vdd-s4-supply | unknown |
| vdd-l2-l10-supply | unknown |
| vdd-l3-l4-l5-l18-supply | unknown |
| vdd-l6-l9-supply | unknown |
| vdd-l7-l12-l14-l15-supply | unknown |
| vdd-l13-l16-l17-supply | unknown |

这六项在机器可读 JSON 中继续保持 null。不把 4.19 的 regulator 输出电压、范围、RPMh ID 或 elish 电路猜作 umi 父供电。

## 旧 UFS 两条私有电源投票尚不能迁移

- qcom,vddp-ref-clk-supply 使用 PM8150 L6。主线 UFS ref_clk 和 PHY ref/ref_aux/qref 负责时钟，ufs-qcom.c 还管理参考时钟门控；**但时钟存在不意味着硬件不再需要这条额外供电投票**。
- qcom,vccq-parent-supply 使用 PM8150A S8C；这是单独的上游投票，不能代替 UFS 标准 vccq-supply（旧 DTS 指向 PM8150 L6）。

Linux 6.12 的 qcom,ufs.yaml、ufs-common.yaml、ufs-qcom.c、ufshcd-pltfrm.c 中均没有这两个私有属性，标准 vcc/vccq/vccq2 regulator 接口则存在。处理结论是**尚无一一映射证据**，不能把私有属性简单复制到主线或宣称移植成功。

## 主线 UFS/PHY 已存在的基础依赖

固定 Linux 6.12 的 sm8250.dtsi 描述：
- UFS Host 在 0x01d84000，GIC SPI 265；8 个 clock、GCC_UFS_PHY_BCR reset、UFS_PHY_GDSC、IOMMU 0x0e0/0x4e0、ufs-ddr/cpu-ufs 两条 interconnect 和 OPP；
- UFS PHY 在 0x01d87000；ref/ref_aux/qref 三个 clock，通过 UFS Host 的 reset provider 复位，使用相同 power domain；
- PHY binding 要求 vdda-phy-supply / vdda-pll-supply，原 SM8250 SoC DTS 没有板级 regulator phandle；Host 标准 vcc/vccq/vccq2 的供电也还没有在 umi 的主线研究 DTS 中接通。

以上节点保持 disabled。时钟、域、IOMMU 配置来自主线 SoC DTS，是**源码存在性**，不等于新内核真实启动测试或时序已经验证。

## 代码、测试与下一阶段门槛

本阶段新增：config/mainline-p1e-ufs-parent-graph.json、scripts/mainline_p1e_ufs_audit.py、tests/test_mainline_p1e.py、mainline-p1e-audit.yml。固定 SHA 源码交叉核对涵盖 Vendor VRM/UFS、主线 RPMh driver/binding、UFS host/PHY binding、driver、SoC DTS。安全回归检查继承的 P1a 六个 disabled 硬件节点和 P1c disabled provider。P1a/P1c DTS 不改；不生成新 DTS、Image 或 boot.img。

首次最小启动前仍须解决：实机 PCB/BOM 与最终 DTBO、完整 PMIC 供电及负载电压、UFS PHY 上电顺序、最小内核/initramfs 可独立编译，以及**非 A/B 设备上经实际验证可逆的恢复方式与 UART/Pstore 早期故障日志**。这几个门禁没有通过前，不能建议刷机。
