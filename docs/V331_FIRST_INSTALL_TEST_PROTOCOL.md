# umi / KernelSU v3.3.1 首次安装真机验收协议

**2026-10-16 现状：**测试者已明确确认官方 v3.3.1 Manager 能在未预装 ksud、无需 adb root 或人工部署时首次完成自动安装并正常提权。此协议保留安全复现和回滚准则；FD Hook 因果归因及安全审计仍未签收。见 [真机验收记录](V331_REAL_DEVICE_ACCEPTANCE.md)。

## 状态与边界

- 目标：Xiaomi Mi 10 (umi)、LineageOS 23.2-20261004-NIGHTLY-umi、Android 16、KernelSU 官方 v3.3.1（固定 Git SHA：0c0fdb960178fa12d80d6cbcfdcb6ad8be6a865d）。
- 前提：PR #3 与 PR #4 **各自最新 HEAD** 的完整内核 Image、vmlinux、umi DTBO 链接成功；必须重新校验对应的 Actions head_sha、源码配置、实验镜像的 SHA-256 和 AVB 元数据。
- 仓库 main / TEST2 v3.3.0 及其成功产物一律保留。实验镜像、Manifest、哈希、警告须使用独立的 v3.3.1 名称；没有真机验证之前不得发布稳定版。
- **禁止在当前正常使用的主力手机上直接删除或覆盖 /data/adb/ksud**，不得由 CI、GitHub 机器人执行刷机。

## 准备与安全条件

1. **首选单独一台测试用 umi**（或已具备完整、可验证且可恢复数据备份的非主力测试环境）；不能使用未经确认的设备快照来宣称完成真实首次安装。准备匹配上述 ROM 的纯净 data 环境，确保测试开始前确实不存在 /data/adb/ksud。
2. 在未刷入实验镜像前，备份测试设备当前 boot、vbmeta、dtbo 和必要的用户数据。准备与 ROM 一致的官方原版 boot.img、已经真机验证的 TEST2 boot.img，核验哈希，提前测试 LineageOS Recovery / Fastboot 的回滚链路。
3. 严格匹配设备 umi、ROM 构建日期、Boot Header v2、镜像 AVB 属性；验证仅替换内核而非无意修改 Ramdisk / DTB / kernel cmdline。测试镜像来源必须可追溯至独立 v3.3.1 Actions 和固定源码 SHA。
4. 除测试人员**明确决定**在测试设备刷入镜像以外，所有操作只做 CI、源码审查和只读检查。本仓库不会自动刷机。

## 首次自动初始化测试（仅限上述已备份的专用测试设备）

1. 测试用干净 /data 启动后，在未开启 Rooted debugging 且不使用 adb root 的情况下，先确认 Android 已启动且 SELinux 为 Enforcing。
2. 安装**官方 KernelSU v3.3.1 Manager**，核验官方 APK SHA-256：`b4a059ace71de2fa65cc7f12b1c58d55fc23ab25e057ee4230ce779742abe450`；首次启动，记录 Manager 版本/UAPI、Root 与模块页面状态、logcat 时间戳。
3. 不执行任何 `adb root`、手动 `ksud install`、手动文件复制或修改 SELinux 的补救命令。验证 Manager 自身能触发 `libksud.so debug su` 并由官方机制完成 `ksud install`。
4. Manager 成功后，通过它授权普通终端应用，在普通应用上下文运行 `/system/bin/su -c id`，应为 uid=0；通过获授权的 Root Shell 只读确认 `/data/adb/ksud` 存在，哈希属于官方 v3.3.1、SELinux 标签为 `u:object_r:ksu_file:s0`。
5. 撤销该终端 Root 授权后必须拒绝提升，再恢复授权应成功。重启后重复 Android 启动、Enforcing、Manager 状态、Root 授权回归。之后才开始模块挂载、复杂 SELinux 策略、长期稳定性测试。
6. 记录成功或失败的精确步骤与运行时证据：`adb logcat -b all -d`、Manager 启动日志、kernel dmesg（仅在已有合法 Root 或 Recovery 环境下）、必要时 pstore。检查 `manager ksud post-exec driver fd installed` 与异常 errno/SIGSYS，并证明是否真的触发自动安装。

## 失败和回滚

- 若无法启动，以测试设备已验证的 Recovery / Fastboot 方案恢复对应 ROM 原版 boot，**先不修改 data、vbmeta 或 dtbo**；收集 pstore 后再分析，不在现场循环试刷。
- 若 Android 正常启动但 Manager 首装失败，保留 ksud 缺失的完整证据和时间线，停止此次验收；不要使用 ADB Root 手动修复后把它记为自动安装成功。
- 如需恢复已有 Root 的测试设备，优先在经验证的 TEST2 boot 与用户数据完整备份前提下操作；回滚 boot 不保证修复所有错误的 data 写入，测试前应明确数据恢复能力。
- 没有专用设备/可验证备份时，本测试阶段维持“未验证”，无需牺牲当前日用机。

## 独立发布门禁

| 核查 | 当前判定 |
| --- | --- |
| TEST2 v3.3.0 真机 Root | 历史已通过，不可转移结论 |
| KernelSU v3.3.1 升级 | 完整 CI 通过；指定 umi 的基本 Root 真机测试通过 |
| PR #4 post-exec task_work FD 适配 | 首次自动安装已由测试者确认；FD 具体机制和静态安全审计仍待完善 |
| v3.3.1 稳定发布 | **阻止** |
