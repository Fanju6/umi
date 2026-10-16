# P0 本地只读复现说明

P0 的公开源码审查结果在 [主报告](README.md)。工具和清单已经入库，**仓库不上传完整内核源码、原厂固件或手机内部数据**。

## 最快验证

```bash
python3 -m unittest discover -s tests -p test_mainline_inventory.py -v
python3 scripts/mainline_inventory.py
```

此时会输出四个 `not_scanned`：只说明 JSON 元数据与安全门禁没有问题，**不表示已在本机检出并审核上游源码**。

## 将实际源码树作为输入

准备四个 Git 工作树，各自 checkout 到 [`config/mainline-research.json`](../../config/mainline-research.json) 指定的精确完整 SHA（不是最新浮动分支）。建议将大型源码克隆放在仓库外的工作目录，例如 `$HOME/kernel-sources/`。若已存在此前的 `.work/kernel`，先核对 Git SHA 再复用，不要重新修改已工作的 4.19 源码目录。

```bash
python3 scripts/mainline_inventory.py --require-all \
  --source vendor_419=/path/to/lineage-4.19 \
  --source mainline_612=/path/to/linux-6.12 \
  --source mainline_70=/path/to/linux-7.0 \
  --source dagu_reference=/path/to/dagu-mainline-linux \
  --output mainline-p0-report.json
```

工具会只读检查四份 `git rev-parse HEAD` 是否与锁定 SHA 一致、已知参考 DTS/配置是否存在、上游是否缺少 umi 主线 DTS，并列出少量 `compatible` 字符串。它不会执行 `git fetch`、`git checkout`、`make`、`fastboot` 或 `adb`。

若上游的检查结果是 `sha_mismatch` / `file_matrix_mismatch`，任务将失败，必须人工复核，不得“自动补齐”或绕过校验。

## P0b 实机信息（只读、无需 Root）

```powershell
adb devices
python scripts/mainline_device_probe.py --output umi-p0b-report.json
```

程序只记录白名单的属性、DT 节点名、平台 UFS/USB/部分 I2C 和电源组件名称，不包含 serial、IMEI、MAC、Android ID、原始 FDT、敏感配置或 userdata；参见 [P0b 映射说明](P0B_HARDWARE_MAPPING.md)。建议人工复核 JSON 后再分享。

## P0b+ 保留内存地址与大小的只读核对

首轮真实 umi 报告显示多个保留内存节点与主线通用 SM8250 默认布局不同。下面这一步用于读取**14 个固定白名单 DT 节点的 `reg` 元数据**（只读、不提权，不读取任何物理内存内容）：

```powershell
python scripts/mainline_reserved_memory_probe.py --output "$env:USERPROFILE\Desktop\umi-p0b-memory.json"
```

程序将 DT 的 `#address-cells` / `#size-cells`、每个白名单节点 `reg` 作为 big-endian 单元解析；若路径不可读则标记 `unreadable`，不会自动切换到 Root 或操作分区。参见 [实机内存布局问题](P0B_REAL_DEVICE_FINDINGS.md)。检查 JSON 后再分享，勿将本地报告自动提交 GitHub。

## P0b+ 内存对照（已经由测试者提交 reg 报告）

从实机生成的 `umi-p0b-memory.json` 已在本阶段被分析，14 个节点全部可读。为避免仅靠节点后缀推导物理地址，新加入固定 6.12 SoC 默认值与真实 `reg` 的 **离线比较器**：

```powershell
python scripts/mainline_compare_memory.py --report "$env:USERPROFILE\Desktop\umi-p0b-memory.json" --output "$env:USERPROFILE\Desktop\umi-p0b-comparison.json"
```

对比工具不连接手机、不需要 Root，也不生成 boot.img；只检查选定范围之间的冲突，**不能替代完整最终 FDT / 固件签收**。已脱敏的关键差异见 [P0b+ 内存分析](P0B_MEMORY_REG_ANALYSIS.md)。

## 第二轮需补充的设备事实

- 只读记录当前 umi 的 `ro.boot` 分区布局、FDT 设备树内的面板与触控物料标识（脱敏）。
- 对比 UFS/USB/PMIC 的电源、复位、总线与 reserved-memory，而不仅对比 `compatible` 名称。
- 将 Android 16 GKI 6.12 与 Torvalds v6.12 区分为两棵源码树，评估 Kernel ABI / Android Vendor HAL 接口差异。
- 确定 UART / Pstore / USB gadget 至少一条可恢复日志通道，再讨论最小启动测试。
- 此阶段继续坚持 **`safe_to_flash=false`**，任何旧版 dagu 分区刷写和 userdata 命令都不进入 umi 的工作流。

实际硬件适配工作的每项通过状态必须来自 umi 的有效运行日志；不以他人设备案例代替。
