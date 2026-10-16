> **历史编译日志（触发方式已更新）：** 现在内核完整编译由相关源码/配置变更的 PR 或 main push 触发，也可在 GitHub Actions 手动启动。**修改本文件不再触发整核构建**。以下按原文保留当时的构建进展。

# 全量内核链接诊断触发

此文件用于按需触发 GitHub Actions 中的「内核诊断编译（非刷机包）」工作流。

- 2026-10-14：固定 LineageOS 23.2 (umi) + 官方 KernelSU 3.3.0 已通过 KernelSU 驱动目录编译（CI #38549163434），现要求编译完整内核和进行最终链接。
- 手动执行（workflow_dispatch）可同时运行原版基线和 KernelSU。此文件变更所触发的自动诊断仅运行 KernelSU 完整编译，失败不得被 continue-on-error 掩盖。
- CI 不上传/发布 boot.img；成功只代表编译/链接验证，不代表可以刷机、能正常 Root 或通过 SELinux/Manager 的真机功能测试。

需要再次触发时，可以编辑此文件，或者在 Actions 页面使用 workflow_dispatch 手动执行。

## 2026-10-14：追踪 path_umount 最终链接修复

- 原完整编译 #38549614526 失败于缺失 `path_umount`。本次触发包含 `ksu_legacy_path_umount` 的整核重新链接，并会执行 `check_build_output.py` 校验 Image / vmlinux / DTB / .config。

## 2026-10-14：完整构建验证安全回归与 umi 设备树校验

- 追踪提交 e02eef4：批量 SELinux 规则失败时放弃全部候选策略；新增 umi-sm8250-overlay.dtbo 的强制检查及 SHA-256 镜像校验清单。
- 本次触发用于验证实际 .config、vmlinux、Image、umi DTBO 和内核驱动归档均被新严格门禁接受；产物仅用于诊断，不打包、不发布 boot.img。
- Root/Manager/Seccomp/SELinux Enforcing 的真机安全检查仍是未解除的 P0 阻塞。

## 2026-10-15：ARM64 sys_call_table 块映射修复后的整核链接验证

- 真机 pstore 表明原版实验内核在 `sys_call_table[42]` 安装 dispatcher 时 `phys_from_virt` 报错，接着仍启用 tracepoint，造成 Android 第一阶段 init 的 stat/fstab 查询返回 ENOSYS；恢复原版 boot.img 能正常开机。
- 第一轮保护逻辑已通过历史快速驱动编译和源码门禁。
- 本轮添加了 Linux 4.19 专用 `pud_sect` / `pmd_sect` 识别，先解析有效块映射物理地址，后执行 `pud_bad` / `pmd_bad` 检查；必须通过整核编译与链接，检查异常路径不得回退成“未安装仍激活”。
- 此次只做 `CONFIG_KSU=y` 下的 Image、vmlinux、umi DTBO 整核校验；**绝不产生新的可刷 boot.img**。CI 通过仍不能证明修复在设备上有效或 Root/Manager/SELinux 可用。

## 2026-10-15：KernelSU 官方 v3.3.1 Linux 4.19 完整编译与链接

在隔离分支 `upgrade/kernelsu-v3.3.1` 上，升级的核心版本已经锁定 `0c0fdb960178fa12d80d6cbcfdcb6ad8be6a865d`。上游源码审查 CI #38697847154 通过，现单独触发 **v3.3.1 内核 Image/vmlinux/DTBO 的全量编译链接**。使用当前相同的 LineageOS umi 源码和 Clang 18 实验工具链做对照；不改变已验证成功的 TEST2 内核，也不自动生成可刷 Boot。

## 2026-10-15：v3.3.1 pkg_observer task_work 兼容修复后的完整链接

提交 501bb447：旧版 task_work_add(current, cb, true) 取代 4.19 中不存在的 TWA_RESUME 枚举；沿用其余已通过的 v3.3.1 兼容补丁。再次触发仅供诊断的整核链接 CI，**不得发布或自动刷写镜像**。


## 2026-10-15：PR #4 post-exec task_work 独立全量编译

PR #4 仍以 PR #3 的 KernelSU v3.3.1 升级为基础，全部代码仅限 experiment/v331-manager-fd-bootstrap 分支。本次全量 Image/vmlinux/umi DTBO 诊断将验证由 sched_process_exec（不能睡眠）投递 GFP_ATOMIC task_work，再在可睡眠的返回用户态前回调中安装 CLOEXEC FD 的原型是否与 Linux 4.19 编译和链接兼容。
必须从 Actions 的 head_sha、内核编译日志与 build-manifest 确认本次实验 HEAD，禁止误用此前的快速驱动检查或旧版编译结果。仍不生成、不上传 boot.img，也不能判定首次 Root 已经完成。


## 2026-10-15：重新验证升级 PR 最新 HEAD 的整核构建

前次完整诊断 CI #38698776009 的 checkout 为旧提交 25b4a18107fc93122a35a3e415bda9eb13f29c66，不能用它代表 PR #3 的最终提交结果。
此次由本文件变更触发的全量 Image/vmlinux/umi DTBO 编译，必须检查该 Actions 运行的 head_sha 等于本次提交，且 build-manifest、编译链接日志和输出检查全部通过。
TEST2 的历史 v3.3.0 真机证据保持不变。scripts/umi-ksud-bootstrap.ps1 严格拒绝从 v3.3.1 checkout 安装其固定的旧版 v3.3.0 ksud；首次自动安装仍是独立未完成验收项。
