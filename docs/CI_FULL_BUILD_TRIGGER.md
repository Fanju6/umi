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
