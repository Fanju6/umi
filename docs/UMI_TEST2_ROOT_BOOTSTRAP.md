# Umi TEST2 真机启动后 KernelSU Manager 显示「获取 root 失败」

2026-10-15 用户反馈：系统 `sys.boot_completed=1`、`uname -r=4.19.325-cip131-st15-perf-g71b13e62f057-dirty`、SELinux `Enforcing`；安装官方 KernelSU v3.3.0 Manager（32601-2）后首页显示「工作中」，但顶部提示「获取 root 失败」。`adb shell su -c id` 提示 shell 找不到 `su`。**这不是证明内核无法提供 Root，而是一次不完整的用户空间部署。**

## 真实内核日志证据（经用户提供，仅记录必要特征）

- `Crowning manager: me.weishu.kernelsu(uid=10205)`：Manager 签名、身份识别路径已完成。
- `ksu fd installed: 4`：Manager 进程相关 FD 注入路径已执行。
- `sys_execve su found`：KernelSU 的 sucompat execve Hook 被调用。
- `open ksud err: -2`（重复）：内核调用 `filp_open(KSUD_PATH, O_PATH, 0)` 返回 `ENOENT`，表示其预期用户空间二进制不存在或路径中有组件缺失。
- 以上日志可以证明特定 syscall Hook 在运行，但**不能证明 Root 授权成功，也不能证明 SELinux/Manager 全部子系统正常**。

## 锁定官方源码对应关系（tiann/KernelSU v3.3.0）

- `kernel/runtime/ksud.h`：`#define KSUD_PATH "/data/adb/ksud"`。
- `kernel/feature/sucompat.c`：`ksu_handle_execve_sucompat_common()` 调用 `filp_open(KSUD_PATH, O_PATH, 0)`；失败时记录 `open ksud err: -2` 并回退原 syscall。
- `manager/.../ui/util/KsuCli.kt`：Manager 可从自身 `nativeLibraryDir/libksud.so` 调用 `ksud debug su`，但缺少系统 `/data/adb/ksud` 时不能完成内核辅助的 Root shell 运行；其 `install()` 会从已成功的 Root shell 调用 `ksud install`。
- `userspace/ksud/src/utils.rs`：`install()` 复制当前 `ksud` 至 `/data/adb/ksud`、标注 `ksu_file` SELinux 标签、解压必要用户空间资源。
- `userspace/ksud/src/defs.rs`：`DAEMON_PATH=/data/adb/ksud`。
- 用户最初使用的自建镜像仅替换了内核，保留原版 Ramdisk，没有执行 `ksud install`。**因此缺失用户空间安装步骤是目前的首要原因，比继续改变内核可信。**

## 只读检查（在 Android 已正常启动状态）

使用 USB 调试的 Windows PowerShell：

```powershell
adb shell getprop ro.debuggable
adb shell getprop ro.build.type
adb shell id
adb shell ls -ld /data/adb
adb shell ls -l /data/adb/ksud
adb shell ls -lZ /data/adb/ksud
adb shell pm path me.weishu.kernelsu
```

如 `ls` 得到 `Permission denied`，只能说明当前 shell 读权限不足；但内核打开该路径明确返回 `ENOENT`。

## 首选补齐用户空间（二进制源和真实性）

**此步骤会写入持久性 `/data/adb/`，不同于以上只读检查。不得在自动化、CI 或未经同意的环境中执行。** 当用户自行选择测试，且已启用 LineageOS 开发者选项中的 Rooted debugging，并确认 `adb root` 后 `adb shell id` 实际 `uid=0(root)`，才可调用与内核相同的 **官方 KernelSU v3.3.0** `ksud`：

- 来源：https://github.com/tiann/KernelSU/releases/download/v3.3.0/ksud-aarch64-linux-android
- GitHub Release API 公布 SHA-256：`8614de6cdc2233c71fd0d1c64381ea10fbe6658651bae9b5a8dab4fe08e6344b`（文件大小 6,286,568 字节）。
- 先使用 ADB Root 实际检查 `id`，再将已校验二进制上传至临时目录 `/data/local/tmp`；然后运行**官方** `ksud install`，并检查安装是否成功与 `/data/adb/ksud` 的权限和 SELinux 标签。**不要使用裸 `cp` 替代官方安装步骤，也不要随意 `setenforce 0` 或重新挂载 system。**
- 若 `adb root` 不可用，则先停在只读阶段；Recovery 能访问 pstore **不代表可解密/mount 正常系统的 /data**。不要推测 Recovery 可写入目标目录。

官方安装完成后的独立复测：重新启动 Manager，确认不再「获取 root 失败」；使用 Manager 授权后的终端运行 `id`，得到 `uid=0(root)` 方算 Root 成功；再在 Enforcing 下验证授权撤销/恢复、系统重启及基础稳定性。

## 未解决及已解决状态

- BOOT：已通过。
- Manager 身份识别：日志确认。
- kernel syscall/FD 路径：部分可观测成功。
- USERSPACE_KSUD：**缺失 / 尚待官方安装并实测**。
- ROOT：**未通过**。
- SELinux Runtime / Manager handshake：仍需 Root 全流程和重启后的实际检查。

不得把 manager「工作中」宣传为完整 Root 功能已完成。

## 2026-10-15：ADB Root 在当前 ROM 上受限

用户实际结果：

```text
ro.debuggable = 0
adb root = ADB Root access is disabled by system setting
adb shell id = uid=2000(shell) ... context=u:r:shell:s0
```

因此此前的“通过 adb root 安装官方 ksud”路线在当前状态**不可执行**，不要继续运行 `adb push` + `ksud install` 命令。Android ADB Root 通常还要求 debuggable 系统构建；`ro.debuggable=0` 的 user build 很可能不显示或不支持 **Rooted debugging**。如果开发者选项有明确的 Rooted debugging 开关可以尝试，否则**不要**为了临时开启权限直接修改 `build.prop`、刷不匹配的调试内核、或关闭 SELinux。

下一步优先进行 Recovery **只读**能力验证。之前已证实 Recovery 可通过 ADB 读取 `/sys/fs/pstore`，但尚未证实当前 Recovery 的运行 UID 或加密 userdata 是否可访问：

```powershell
adb reboot recovery
adb devices
adb shell id
adb shell getprop ro.build.type
adb shell ls -ld /data /data/adb
adb shell cat /proc/mounts | Select-String ' /data '
adb shell ls -lZ /data/adb/ksud
```

如果 Recovery 里 `uid=0`、`/data` 已正确挂载并可访问实际的 `/data/adb`，再对**匹配的同版本官方 ksud** 设计独立的用户自主安装步骤并验证 SELinux context；所有操作必须保留可回滚路径。若 userdata 在 Recovery 中尚未解密或挂载，不要通过新建 Recovery RAM 临时 `/data` 目录伪装真实存储；不要格式化 userdata。

仍以实际 `KernelSU: open ksud err: -2` 及 Manager 的 Root 失败为首要排查目标；无数据权限前不能断言真实 `/data/adb/ksud` 文件一定不存在，只能确认内核打开该绝对路径时得到 ENOENT。

## 2026-10-15 14:25：用户启用 Rooted debugging 后官方 ksud 成功安装（更新）

前面的 “ADB Root 不可用” 只代表**开关关闭时的观察结果**，**不是**当前 ROM 的永久限制。用户确实在开发者选项发现并开启了 **Rooted debugging**。同样 \`ro.debuggable=0\` 的状态下，重新运行 \`adb root\` 得到 \`restarting adbd as root\`，\`adb shell id\` 返回：

\`\`\`text
uid=0(root) gid=0(root) ... context=u:r:su:s0
\`\`\`

官方 KernelSU 3.3.0 ksud 下载后 SHA-256 验证通过（\`8614de6cdc2233c71fd0d1c64381ea10fbe6658651bae9b5a8dab4fe08e6344b\`），用户已使用以下流程成功部署：\`adb push\` 至 \`/data/local/tmp/ksud\`、\`chmod 700\`、\`/data/local/tmp/ksud install\`。随后确证实际持久路径：

\`\`\`text
-rwx------ 1 root root u:object_r:ksu_file:s0 6286568 ... /data/adb/ksud
\`\`\`

用户反馈：**KernelSU 管理器现已正常，不再有之前的 Root 获取失败问题**。说明官方用户空间部署是此前症状的关键缺失环节；**不必为了这个问题继续重编或重刷 boot.img**。

注意：ADB Root 成功仅证明调试链路可以获得 UID 0，并不独立证明普通应用的 KernelSU 授权成功。Manager 首页状态恢复是积极证据，但完整 Root 验收还需一款普通终端应用申请授权并实际输出 \`uid=0(root)\`。不要求禁用 SELinux 或安装额外 Root 框架。

### 推荐的分阶段验收

1. 保持 TEST2 现有镜像，打开 KernelSU 管理器确认「工作中」、无红色 Root 错误。
2. 在 Manager 的 **超级用户** 中允许可信终端应用（例如 Termux），再由该应用运行 \`/system/bin/su -c id\`；应看到 \`uid=0(root)\`，同时检查 Manager 授权记录。
3. 拒绝一次授权、确认无法获得 root，再恢复允许（注意不要对未知第三方应用授权）。
4. 验证 \`adb shell getenforce\` 仍为 \`Enforcing\`。在保存数据后做一次正常重启，复测 Manager、Root 与 \`/data/adb/ksud\` 是否仍正常。
5. 验证后在日常使用中关闭 **Rooted debugging** 以减小 ADB 提权攻击面；关闭前确保普通应用 Root 授权已完成，不再依赖 adb root 进行安装。

当前状态：\`BOOT_SUCCESS / KSUD_INSTALL_SUCCESS / SELINUX_LABEL_OK / MANAGER_REPORTED_NORMAL / APP_ROOT_TEST_PENDING / REBOOT_PERSISTENCE_PENDING\`。
