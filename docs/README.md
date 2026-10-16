# 文档索引

优先阅读当前文档；历史文档保留早期故障和阶段性结论，不代表目前仍无法启动或无法 Root。

| 分类 | 文档 | 说明 |
| --- | --- | --- |
| 当前 | [状态与真机验收](STATUS.md) | 版本、验证内容与发布边界 |
| 开发 | [构建指南](BUILD.md) | 上游、补丁、CI 和产物 |
| 开发 | [架构说明](ARCHITECTURE.md) | 代码目录与运行流程 |
| 设备 | [设备预检](DEVICE_PREFLIGHT.md) / [Boot 布局](UMI_BOOT_LAYOUT.md) | 只读检查与恢复约束 |
| 证据 | [v3.3.1 真机记录](V331_REAL_DEVICE_ACCEPTANCE.md) | 用户原始回显及证据等级 |
| 证据 | [v3.3.1 CI 报告](V331_CI_RESULTS_20261015.md) | 构建、镜像校验和 SHA-256 |
| 测试 | [首次自动安装验收协议](V331_FIRST_INSTALL_TEST_PROTOCOL.md) | 无预装 ksud 的安全测试与回滚 |
| 深入 | [SELinux 4.19 移植](SELINUX_419_PORT.md) | 特定 API 和安全风险 |
| 维护 | [工作流维护](CI_WORKFLOW_MAINTENANCE.md) | CI 触发条件、文档检查与优化路线 |
| 研究 | [SM8250 Linux 6.12 / 7.0 P0 对照](mainline-port/README.md) | 固定源码、驱动差异、风险与只读验证工具 |
| 历史 | [开发历史与故障档案](history/README.md) | TEST2、首版启动失败、Manager 原型 |

**文档状态标记：**“命令回显”有真实设备或 CI 输出，“测试者确认”代表已经报告成功但未必提供原始全流程日志，“静态审计 BLOCK”表示代码安全分析尚未签收。这三类证据不能互相代替。
