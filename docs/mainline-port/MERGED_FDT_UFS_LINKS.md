# umi 旧内核合成 FDT 的 UFS 供电 phandle 对照

此步骤承接已收到的 12 条完整 DTBO 报告。索引 11 的 root model 为 xiaomi umi，12 项 root-compatible 相同，DTBO 条目的 id/rev/custom 全为零；仅凭此表不能断言 Bootloader 最终选了哪个 overlay。

下一项真正有价值的证据是 **旧 Linux 4.19 当前运行的、Bootloader 已合成的实际设备树**：UFS Host/PHY 的八条 regulator 引用分别指向哪个 provider phandle。读取它比继续重复 DTBO 各条目索引更直接支持后续 Linux 6.12 DTS 设计。

## 安全和隐私

新增 [scripts/mainline_merged_fdt_ufs_links.py](../../scripts/mainline_merged_fdt_ufs_links.py)，需要用户此前明确授权的 Root。脚本先验证 device=umi，再使用 binary-safe ADB exec-out 只读读取 /sys/firmware/fdt；最多接受 16 MiB 数据，**全部仅存在电脑进程内存**。不保存、上传或显示原始 FDT，因为其可能包含非公开设备元数据。

解析器只输出运行时根 model、compatible、根 qcom,board-id（若存在）和 UFS Host/PHY 八个已知供电属性引用的 phandle 值，尝试与运行树里明确具有旧 PM8150/PM8150A resource-name 或 regulator-name 的 provider 对应。完全不读取 Pstore 日志、Raw RAM、userdata，也不挂载 debugfs、修改稳压器、重启、测试 Recovery 或写分区。对未知 provider 不暴露任意设备路径。

Windows PowerShell：

~~~powershell
cd C:\Users\fanju\umi-p0b
git pull --ff-only
python scripts/mainline_merged_fdt_ufs_links.py --probe --output "$env:USERPROFILE\Desktop\umi-merged-fdt-ufs.json"
~~~

如果本机旧内核未提供 /sys/firmware/fdt，脚本会报读取失败，不应为了让脚本运行而改写设备或去挂载新的文件系统。在报告成功后，请分享 JSON，而不是原始 FDT。

## 分层证据

- 当前观察：9 条旧版 regulator 均 enabled；9 个旧 RPMh 资源名称可在运行设备树看到；Android DTBO v0 12 条目中索引 11 是唯一 xiaomi umi。
- 固定 vendor 源码：umi-sm8250-overlay.dts 的 root model 为 xiaomi umi，qcom,board-id 为 <43 0>，该 board-id 与 DTBO 容器外层为零的 id 不是同一个字段；共享 xiaomi-sm8250-common.dtsi 声明 UFS 八条供电属性。
- 本探针若成功：识别当前旧内核最终 FDT 中哪些 UFS phandle 能和旧 regulator provider 对应；这并不等于证明六组主线 PM8150 输入 parent 的真实电气布线、旧私有负载投票向 6.12 的迁移，或 Bootloader DTBO 的精确索引选择算法。
- 后续主线研究 DTS 仍保持所有 UFS/USB 与测试性 PMIC provider disabled；尚未可恢复试启动。

safe_to_attempt_mainline_boot=false；safe_to_flash=false；稳定 main 不修改。
