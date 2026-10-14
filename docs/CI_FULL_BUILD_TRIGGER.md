# 全量内核链接诊断触发

此文件用于按需触发 GitHub Actions 中的「内核诊断编译（非刷机包）」工作流。

- 2026-10-14：固定 LineageOS 23.2 (umi) + 官方 KernelSU 3.3.0 已通过 KernelSU 驱动目录编译（CI #38549163434），现要求编译完整内核和进行最终链接。
- 构建包含原版基线和集成后的 KernelSU 两个 Job，失败不得被 continue-on-error 掩盖。
- CI 不上传/发布 boot.img；成功只代表编译/链接验证，不代表可以刷机、能正常 Root 或通过 SELinux/Manager 的真机功能测试。

需要再次触发时，可以编辑此文件，或者在 Actions 页面使用 workflow_dispatch 手动执行。

## 2026-10-14：追踪 path_umount 最终链接修复

- 原完整编译 #38549614526 失败于缺失 `path_umount`。本次触发包含 `ksu_legacy_path_umount` 的整核重新链接，并会执行 `check_build_output.py` 校验 Image / vmlinux / DTB / .config。
