# KernelSU v3.3.1 迁移工作单（隔离分支）

**隔离分支：** `upgrade/kernelsu-v3.3.1`，不覆盖此前已经经过真实 umi 设备验证的 TEST2 (KernelSU 3.3.0)。

## 上游

- 2026-10-15 查证 GitHub Release 的最新正式版为 `v3.3.1`（2026-10-12 发布）。
- 原锁定：`v3.3.0` / `932014ab5b2c9b74a3d11e2ec4d17dd10fc9442e`
- 新锁定：`v3.3.1` / `0c0fdb960178fa12d80d6cbcfdcb6ad8be6a865d`
- 官方下载地址：https://github.com/tiann/KernelSU/releases/tag/v3.3.1
- 官方 Manager APK `KernelSU_v3.3.1_32680-release.apk`，SHA-256 `b4a059ace71de2fa65cc7f12b1c58d55fc23ab25e057ee4230ce779742abe450`
- 官方 arm64 ksud `ksud-aarch64-linux-android`，SHA-256 `049491e2b4cc0a6c913d3920cb90b8c94c9e8ca96c0ee92818293304973bfb1b`
- 差异：79 次提交，触及 SELinux、KernelSU Hook、Manager/UAPI、挂载命名空间、sucompat 等。**原 v3.3.0 补丁不可直接视为已验证。**

## CI 顺序与门禁

1. 固定 Git commit，禁止从浮动 main 分支拉取。
2. 运行旧版 4.19 适配补丁，由精确锚点拒绝不兼容改动；遇上游漂移先对照真实源码。
3. 修复编译兼容后运行完整 Linux 4.19 Image/DTB 链接与安全门禁。
4. 针对首次 Manager 获取驱动 FD / ksud 缺失进行独立修复，不在升级中偷偷更改已经成功启动的 TEST2 路径。
5. 仅在全部 CI 和经过明确的真机回归策略之后，才考虑新镜像并实测 Android 启动、Enforcing、Manager 初始化、su 授权拒绝/恢复、重启持久性。

**本分支不得因为源码 CI 通过就将 TEST2 v3.3.0 的真机证明转移给 v3.3.1。** 旧的 `umi-ksud-bootstrap.ps1` 是 TEST2/v3.3.0 专用辅助工具；在新核心完成验证前不得用它配套新内核，或者直接给已 Root 的手机手动覆盖 ksud。

## 首轮 v3.3.1 编译修复

快速编译 CI #38697847147 于 manager/pkg_observer.c:48 报错 TWA_RESUME 未声明。v3.3.1 新增的 task_work_add(current, cb, TWA_RESUME) 在 Linux 4.19 的 API 应以 notify=true 表达。已增加有严格锚点与单元测试的独立版本兼容补丁，不改动现代内核路径；尚需重新编译验证。
