# P1d · umi RPMh 资源 ID 证据与 UFS 额外供电依赖

**2026-10-16 · 源码审计阶段，不使能内核硬件，不生成 boot.img，不刷机。**

## 原 P1c 的一个关键证据缺口已经缩小

对照 [umi 4.19 锁定 SHA 的 `kona.dtsi`](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom/kona.dtsi#L5155)：
`#include "kona-regulators.dtsi"` 将旧内核的 RPMh VRM regulator 定义引入底层 Kona DTS。[`umi-sm8250.dtsi`](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom/umi-sm8250.dtsi#L6-L8) 同时引用 Xiaomi 共用节点，其中包含 UFS 供电。需区分**基础 Kona DT + umi 后续覆盖**与完全相同的最终设备树：当前还未逐个解析完整原厂 DTBO 合成结果。

[`kona-regulators.dtsi`](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom/kona-regulators.dtsi) 中，七个 UFS/USB2 PHY 供电对应的 VRM resource 标识清晰可见：

| Legacy PM8150 label | 4.19 RPMh VRM 资源名 | 6.12 RPMh 子节点 | 旧内核实测 |
| --- | --- | --- | ---: |
| `pm8150_s4` | `smpa4` | `smps4` | 1.800 V |
| `pm8150_l2` | `ldoa2` | `ldo2` | 3.072 V |
| `pm8150_l5` | `ldoa5` | `ldo5` | 0.880 V |
| `pm8150_l6` | `ldoa6` | `ldo6` | 1.200 V |
| `pm8150_l9` | `ldoa9` | `ldo9` | 1.200 V |
| `pm8150_l12` | `ldoa12` | `ldo12` | 1.800 V |
| `pm8150_l17` | `ldoa17` | `ldo17` | 2.504 V |

**结论与证据等级：** 旧版 RPMh 资源统一指向 VRM suffix `a`，配合主线 v6.12 的 [`qcom,rpmh-regulator.yaml`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/Documentation/devicetree/bindings/regulator/qcom,rpmh-regulator.yaml)，可以把主 PM8150 的**候选** `qcom,pmic-id = "a"` 从单纯引用 elish 提升到“有 umi BSP 自身 resource 名作依据”。但不证明新内核的完整 PMIC enumeration、TCS/VRM 命令路由和运行时探测，仍然 **不可以将 P1c 的 disabled provider 改成 okay**。

## UFS 的两条附加旧版厂商依赖

[xiaomi-sm8250-common.dtsi](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom/xiaomi-sm8250-common.dtsi#L43-L73) 另外明确存在：

- `qcom,vddp-ref-clk-supply = <&pm8150_l6>`：旧版 UFS 参考时钟相关供电投票。Linux 6.12 的 `ufs_mem_hc` 使用不同的标准时钟和控制器绑定，不能直接复制 Vendor 属性。
- `qcom,vccq-parent-supply = <&pm8150a_s8>`：另一个 PMIC（名称为 `pm8150a`）的 S8 参与旧版 VCCQ parent 关系；它**不是**普通的 `vccq-supply` 同义字段。须独立审查与主线 PM8150L/BOB 或其它板级父供电有无关系，绝不能根据 elish 推测。

本轮把原来 8 条标准 UFS/USB2 PHY 供电依赖之外的这两条明确拆开，**完整迁移前至少有 10 条旧版电源关联需要分别审查**（含共享轨重复引用）。仍无法仅凭旧 DTS 得出六组主线 RPMh parent input 的实际 umi 电路连线。当前没有真实串口/Pstore 的高版本启动日志。

## 实现结果

- [P1d 机器可读证据图](../../config/mainline-p1d-rpmh-evidence.json)：七轨输出、VRM resource suffix、上游组名、两条追加 UFS 边、PMIC ID 置信等级与不许使能的边界。
- [离线源码审计器](../../scripts/mainline_p1d_rpmh_audit.py)：静态验证 pinned 4.19 `kona-regulators.dtsi`、`kona.dtsi`、`xiaomi-sm8250-common.dtsi`、`umi-sm8250.dtsi`，再核对固定 v6.12 binding 和 elish 示例。零设备连接、零硬件操作、零刷机。
- [测试](../../tests/test_mainline_p1d.py)：若有人把 `unknown` 父供电改为别机的 phandle、复制旧电压或将 PMIC ID 猜测设为已通过主线探测，会拒绝。
- 单独 [P1d CI 工作流](../../.github/workflows/mainline-p1d-audit.yml)：无需巨大内核仓库稀疏检出，直接获取固定 SHA 小型源码文件、运行源码交叉核对，避免被此前需要下载大量 Linux DTS 的工作流拖住。

**还不能做的事情：** 把全部电源轨自动写入已启用的主线 DTS，或为 umi 编译/刷写 Linux 6.12 Boot。P1c 禁用态 DTS 保持不变。当前阶段标志为 `P1D_LEGACY_VRM_SUFFIX_A_EVIDENCE`、`P1D_MAINLINE_PMID_NOT_TESTED`、`P1D_PARENT_WIRING_UNKNOWN`、`SAFE_TO_FLASH_FALSE`。

后续 P1e 建议优先核对实际 `vph_pwr` / PM8150A S8 / BOB 的供应关系，解决 UFS parent dependency，再处理 PM8150B USB Type-C/PD，不要一并使能全部外设。
