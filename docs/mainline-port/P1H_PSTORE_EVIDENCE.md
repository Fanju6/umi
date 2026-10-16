# P1h · umi Pstore 实测结果与 Linux 6.12 ramoops 接口审计

**2026-10-16；仅研究。无 ADB/Root/重启/刷写或物理 RAM 访问。safe_to_flash=false，safe_to_attempt_mainline_boot=false。**

## P1g 用户实际完成了什么

用户在 4.19 正常运行的 umi 上执行已提交的 P1g 无 Root 只读探针，提供如下脱敏 CLI 摘要：

| 字段 | 真实观察 |
| --- | --- |
| pstore_directory_present | true |
| pstore_filesystem_mounted | true |
| pstore_record_types_visible | console、pmsg |
| 本次未见对应类别 | dmesg、ftrace |
| safe_to_flash | false |

P1g 探针通过文件名模式 console-ramoops*、pmsg-ramoops*、dmesg-ramoops*、ftrace-ramoops* 分类。这说明**当前 Android 16 / Linux 4.19 环境在 /sys/fs/pstore 中有 ramoops 命名风格的 console/pmsg 文件**。但本阶段仅收到脱敏控制台摘要、**没有读取用户保存在 Desktop 的完整 P1g JSON**、没有读取任何文件正文，更没有直接查验实际设备上的 ramoops platform device 或 DT reserved-memory。

因此，这不是对后端真实物理地址、跨重启保留、panic/dmesg 记录或 Linux 6.12 兼容性的验证。尤其不能从本次未列出 dmesg 文件断言设备不支持内核崩溃日志：文件缺席可能只是尚未发生相应记录或被系统清理。

## 锁定主线 6.12 源码的新证据

基线 adc218676eef25575469234709c2d87185ca223a：
- fs/pstore/ram.c 中 console_size / pmsg_size 分别有独立配置；另有 record_size、ftrace_size，device tree compatible 为 ramoops。
- Documentation/devicetree/bindings/reserved-memory/ramoops.yaml 说明 ramoops 应占用独立的 reserved-memory reg，分别支持 record-size、console-size、pmsg-size、ftrace-size，还支持 max-reason、mem-type 等约束。
- 内核支持 ramoops 的**源码事实**不代表可直接使用原厂 DT 的 XBL/UEFI 日志区域。绝不能把 res_xbl_uefi_log_region@80880000 当作 ramoops，也不能借用 elish/dagu 的 RAM 起止地址、大小或 reserved-memory 内存布局。

这次不创建任何新的 ramoops DT 节点，尤其不写 reg、size、memory-region、console-size / pmsg-size 的物理参数。P0c 全部保留区域已核实不重叠，且某些早期 Boot/Firmware 划分可能不适用于存放持久日志；需后续单独核验实际系统所用的存储后端和有效映射范围。

## 本轮代码与验收

- config/mainline-p1h-pstore-evidence.json：保留用户共享的摘要真实值，显式标注来源为 CLI 摘要、没有完整 P1g JSON，全部启动、恢复、物理内存相关 gates 为 false。
- scripts/mainline_p1h_pstore_audit.py：默认离线，仅比对 P1g/P1h 合同与安全门禁；在 CI 中用固定版本的主线 fs/pstore/ram.c 和 ramoops.yaml 跨源码核对。没有 ADB 子进程。
- tests/test_mainline_p1h.py：17 项含 P1g 完整脱敏报告的模拟输入校验、反造假与安全拒绝测试。
- .github/workflows/mainline-p1h-pstore.yml：固定 SHA 拉取两份文件并运行单元与前阶段回归。

## 用户可以立刻离线复核（不会连接手机）

~~~powershell
cd C:\Users\fanju\umi-p0b
git pull --ff-only
python scripts/mainline_p1h_pstore_audit.py
python -m unittest discover -s tests -p test_mainline_p1h.py -v
~~~

还可以**只在本地验证**之前生成的完整脱敏 JSON，仍然不连接手机：

~~~powershell
python scripts/mainline_p1h_pstore_audit.py --report "$env:USERPROFILE\Desktop\umi-p1g-logs.json"
~~~

上述带 report 的版本仅验证 JSON 字段白名单、设备 umi、4.19 内核和 console/pmsg 两类记录的匹配性；报告不上传、不复制到仓库，也不会默认读取 Pstore 正文或重复运行 ADB。成功时仅输出 local_report_verified=true，**不更改源代码中的硬件验证状态**。

## 后续具备哪些条件才能讨论实际启动

- 应从 umi 特有的只读实际 DT/平台节点确认 ramoops 后端是否存在及有效的 reserved-memory 区间，且必须与 P0c 34 节点布局、安全固件区域逐一核对；现阶段还没有这样的证据。
- 另行经真实验证证明 console/pmsg 或 dmesg 内核故障可跨重启保留，且在系统故障后有可访问的实际日志；不能通过制造 panic 来测试。
- 必须有非 A/B 恢复介质、恢复流程、真实 Recovery 能力、可逆的 4.19 基线验证；不能直接尝试可启动 6.12 或开启 UFS/USB/PMIC。
- 这些条件之外还存在 P1e/P1f 供电输入与两项私有 UFS 负载投票未知。安全状态始终 safe_to_flash=false。

## 锁定源码

- https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/fs/pstore/ram.c
- https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/Documentation/devicetree/bindings/reserved-memory/ramoops.yaml
- [P1g 只读探针和结果框架](P1G_RECOVERY_LOG_GATES.md)
- [P0c 内存安全核对](P0C_FULL_MEMORY_AND_DTC.md)
