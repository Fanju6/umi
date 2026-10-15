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
