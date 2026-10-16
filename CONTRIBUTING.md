# 贡献与维护

1. **确认版本**：`main` 为官方 KernelSU v3.3.1，v3.3.0 TEST2 保存在历史提交中。升级版本前核实用户空间 `ksud`、ROM、内核 SHA 一致。
2. **固定上游**：修改前检查 `config/upstream.env` 的 LineageOS / KernelSU Git SHA，不跟随浮动分支。
3. **小步提交**：新兼容改动应是针对确定源码锚点的脚本，须在无法匹配时拒绝，不使用危险指针强转或降低 SELinux 来隐藏问题。
4. **包含回归**：使用 `python3 scripts/apply_patches.py --plan` 核对统一补丁清单，运行 `python3 -m unittest discover -s tests -v`；内核改动通过源码审计、驱动编译与完整内核 CI，并记录工作流链接。
5. **区分证据**：如实列出是否有真机命令回显、测试者确认或源码假设。测试不能外推到其他设备/ROM。
6. **中文 PR**：标题、说明、提交信息使用中文；禁止上传未经脱敏的 pstore、系统日志、序列号或个人信息。
7. **发布约束**：在审计门禁解除且独立确认可恢复以前，不自动刷机或通过 Actions 生成稳定发行版。

参见 [构建](docs/BUILD.md)、[架构](docs/ARCHITECTURE.md)、[状态](docs/STATUS.md)。
