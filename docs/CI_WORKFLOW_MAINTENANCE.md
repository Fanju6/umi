# 工作流维护与下一步优化

本页描述开发分支上经过审查的 CI 触发语义；具体以 GitHub Actions 现行工作流文件为准。

## 优化目标

原始 `source-audit.yml` 在**全部 push** 和 `pull_request` 上都完整拉取上游并执行静态审计，文档修改也会触发大型任务，并在有 PR 的分支上重复执行。早期 `kernel-compile.yml` 靠编辑 `docs/CI_FULL_BUILD_TRIGGER.md` 触发编译，不是稳定的代码变更门禁。

第一轮保守优化：

- `docs-check.yml` 仅运行 Python 脚本及文档相对链接检查，针对文档 PR，成本小、结果明确。
- `source-audit.yml`：只在相关代码、配置、测试或工作流文件变动的 PR，以及 main 对应变更时自动运行；支持手动触发。
- `kernel-smoke.yml`：保留原来的快速 Kbuild 任务与日志，只改相关代码 PR、main push 的触发行为。
- `kernel-compile.yml`：相关构建代码变更时自动运行完整 Image / DTBO 链接；不再修改文档哨兵以“唤醒” CI。仍保留手动 `workflow_dispatch`。
- **不修改** KernelSU 上游 SHA、十余项补丁顺序、工具链、产物检查、SELinux/Manager BLOCK 和镜像内容。

## 仍待下一轮整理

1. 四个工作流中兼容补丁应用顺序存在重复；后续可先设计一个带 v3.3.0/v3.3.1 模式检查的统一入口，并在完整镜像构建中对照运行结果，**不要直接删除版本门禁**。
2. `experimental-v331-boot.yml` 当前仅允许 v3.3.1 独立分支，并由文档标记或手动触发。它尚未进入默认分支，因此不能草率删掉用于分支运行的历史触发方式；等待对应集成/发布流程调整。
3. 测试日志和 Manifest 可逐步标准化为单份可复用构建证明，减少多次下载上游和冗余构建。
4. 历史实验 Artifacts 包含 `UNVERIFIED` 标识，属于不可篡改的旧产物标识。即便对应版本已有真机功能反馈，也不应在没有新的发布安全验收之前改名为 `STABLE` 或清除 `safe_to_flash=false`。

整个工作流优化独立于文档 PR、不能替代真机安全评估和恢复测试。
