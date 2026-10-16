> **历史文档哨兵（已退役）：** v3.3.1 构建已转为 `main` 上的手动 `workflow_dispatch`，此文件的修改**不再触发 Boot 构建**。本页以下文字保留首次实验的来源和审查记录；当前使用 [构建指南](BUILD.md) 与 [验收状态](STATUS.md)。

> **历史触发记录：** 下文早期“尚需真机开机/首装”的结论已被后续 v3.3.1 真机验收更新，参见 [最新状态](STATUS.md)。文档路径触发机制当前保留，用于在尚未合入默认分支时显式构建独立 v3.3.1 版本；不自动刷机或发布。

# 独立 KernelSU v3.3.1 Manager FD 实验镜像构建触发

- 构建分支：`experiment/v331-manager-fd-bootstrap`；只允许该分支上的官方 v3.3.1 固定 SHA + umi 固定 LineageOS 源码。
- 此文件变更触发 `.github/workflows/experimental-v331-boot.yml`，独立编译、封装并离线核验一个 `MANAGERFD-UNVERIFIED` 镜像。
- 先应用 Linux 4.19 既有安全兼容补丁，再应用 `patch_task_work_331.py` 与使用 GFP_ATOMIC + task_work 的 `patch_manager_postexec_fd_419.py`。
- SHA256 验证官方 ROM 20261004 的 boot.img，沿用原版 Ramdisk/DTB/Header/AVB 属性并运行 `check_experimental_boot.py`。
- 镜像及哈希只上传至有 7 天保存期的全新 Artifact；**绝不替代 TEST2 产物、绝不自动刷入手机、绝不标记稳定版**。
- 无论 CI 结果如何，Android 16 实机开机、SELinux Enforcing 与零预装 ksud 的首次 Manager 自动安装都尚需根据 `docs/V331_FIRST_INSTALL_TEST_PROTOCOL.md` 在可恢复的专用测试设备上验收。

## 2026-10-15 首次独立镜像实验

在原 v3.3.1 旧提交完整链接 #38698776009 成功，且 PR #4 后续 post-exec task_work 快速驱动编译与源码审查成功的前提下，发起一个单独的实验镜像构建。该流水线会自行执行全量内核编译和结构校验，因此早前的成功不能替代本次产物的检查。
