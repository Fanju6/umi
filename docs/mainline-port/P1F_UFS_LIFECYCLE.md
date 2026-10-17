# P1f：umi UFS 私有供电投票的驱动生命周期审计

**2026-10-16；纯源码研究；safe_to_flash=false，禁止使能 PMIC/UFS/USB 或生成可刷写镜像。**

## 一、P1e 之后的新证据：不仅仅是 DTS 属性名

LineageOS 4.19 固定 SHA 71b13e62f057a649b77fe4062feb73ee72ad609c 的 drivers/scsi/ufs/ufs-qcom.c 已核查到 ufs_qcom_parse_reg_info、ufs_qcom_init、ufs_qcom_suspend、ufs_qcom_resume、ufs_qcom_config_vreg、ufs_qcom_enable_vreg 和 ufs_qcom_disable_vreg。

| 4.19 的特殊 UFS 属性 | 旧供电轨 | Init | Link OFF | Hibern8 | Resume |
| --- | --- | --- | --- | --- | --- |
| qcom,vddp-ref-clk-supply | pm8150_l6 | ufs_qcom_enable_vreg（先配置后 regulator_enable） | regulator_disable | 调整为 min 负载投票 | 根据电源管理状态恢复 enable 或 max 投票 |
| qcom,vccq-parent-supply | pm8150a_s8 / RPMh smpc8 | ufs_qcom_config_vreg（负载投票） | Link 非 Active、auto BKOPS 未启用时撤销负载投票 | 同左 | 恢复负载投票 |

旧 Xiaomi common DTS 中两条属性对应 qcom,vddp-ref-clk-max-microamp = <100> 与 qcom,vccq-parent-max-microamp = <210000>。这些是 **旧 BSP 的最大请求负载设置**，不能宣称为实测运行电流或 Linux 6.12 的安全负载值。

旧驱动先通过 DT phandle + devm_regulator_get 获取对象。ufs_qcom_config_vreg 在 regulator_count_voltages > 0 时调用 regulator_set_load；只有 min_uV 和 max_uV 都非零时才会调用 regulator_set_voltage。解析器为旧 vddp-ref-clk 设置 1.2V 缺省值，为 vccq-parent 设置 0 缺省值。**这些值不是 6.12 的可移植电气规格。**

特别重要：该 4.19 UFS driver 对 vccq-parent 执行 config_vreg/load vote，未通过此路径调用 regulator_enable。也不能据此断言该电源在系统中一定 disabled，因为可能有其他消费者或启动固件投票。Vendor 字段名字含有 parent 也不是 PCB 布线证据。

## 二、PM8150A S8C 可能存在多消费者

固定 Kona DTS 中 vdd-wlan-rfa2-supply = <&pm8150a_s8>，固定 Xiaomi common DTS 中 qca,bt-vdd-rfa2-supply = <&pm8150a_s8>。因此 S8C 在**源码引用层面**还由 WLAN / Bluetooth 使用，不能因为 UFS 自己的 suspend 想降载便假定整个物理 S8C 可关断。该事实不证明无线模块真实已上电或 umi 主 PM8150 的六组输入供电属于此轨。

## 三、Linux 6.12 对比与仍未解决的问题

锁定 Torvalds 6.12 adc218676eef25575469234709c2d87185ca223a：drivers/ufs/host/ufshcd-pltfrm.c 读取标准 vdd-hba / vcc / vccq / vccq2，ufs-qcom.c 管理 ref_clk、PHY 的 PM 过程。已核查的驱动和 qcom,ufs.yaml / ufs-common.yaml 中没有这两个 Vendor 专有属性的直接使用。

**这不证明两个额外 regulator 的电气需要消失**，也不能直接将旧私有属性照搬进上游 DTS。迁移前仍需验证 umi 的 S8C/VDDP 电源网络、负载需求及上游父电源拓扑，不借用 elish 的电路与电压。

## 四、工程产物与证据等级

- config/mainline-p1f-ufs-lifecycle.json：两个 UFS 特殊供电的 Init / Link OFF / Hibern8 / Resume 行为及 S8C 的两条其他引用。
- scripts/mainline_p1f_ufs_lifecycle.py：离线审计数据合同；在 CI 中对固定版本的七份公开源码执行真实驱动函数验证，并交叉核查 P1e 六组未知父供电。
- tests/test_mainline_p1f.py：13 项针对错误使能、负载/电压混淆、私有供电误映射、源证据遗漏和安全门禁的测试。
- .github/workflows/mainline-p1f-audit.yml：认证 GitHub API 固定 SHA 小文件抓取，无手机操作，无 Boot 产物。

**证据等级**：供电调用路径/属性属于已固定公开 4.19/6.12 源码证据，P1b 实机电压仍仅代表旧 4.19 的运行时状态；6.12 仅有离线 DTS 验证，没有真机 PMIC/UFS 探测。

P1a 和 P1c DTS 均未改变。P1e 六组真实父供电 phandle 仍为 null，UFS 两个 Vendor 额外供电仍为 unmapped。所有 hardware/flash gates 均为 false。

## 五、下一阻塞和首次可恢复启动门槛

下一阶段优先核对真实 PCB 供电链（六组 PM8150 parent、S8C、BOB、VPH_PWR）、UFS PHY reset/时钟/电源完整时序以及最终 DTBO；随后验证**非 A/B** boot header v2 设备的日志通路、Recovery 和恢复到已知可用 4.19 的能力，再评估最小 Linux 6.12 编译和仅在可恢复实验机上进行首次启动。当前绝不能刷写。

### 源码链接

- [Vendor 4.19 UFS QCOM 驱动](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/drivers/scsi/ufs/ufs-qcom.c)
- [Vendor umi common DTS](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom/xiaomi-sm8250-common.dtsi)
- [Vendor Kona DTS](https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom/kona.dtsi)
- [主线 Linux 6.12 QCOM UFS](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/ufs/host/ufs-qcom.c)
- [主线 Linux 6.12 UFS platform](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/ufs/host/ufshcd-pltfrm.c)
