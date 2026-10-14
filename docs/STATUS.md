# 开发状态与安全门禁

## 2026-10-14：第一次落地

- **目标设备：** Xiaomi Mi 10（umi），LineageOS 23.2，Linux 4.19.325。
- **唯一优先方案：** tiann/KernelSU 官方 v3.3.0；不使用 KernelSU Next。
- **源码 SHA：** LineageOS 71b13e62f057a649b77fe4062feb73ee72ad609c；KernelSU 932014ab5b2c9b74a3d11e2ec4d17dd10fc9442e。
- **当前阶段：** 可以自动获取、固定来源、接入 Kconfig/Kbuild、应用初步安全补丁，并开始 GitHub Actions 诊断；还没有经过完整内核编译和真机启动。

## 已完成的具体修正

1. Seccomp：Linux 4.19 无 action_cache，不允许新版 KernelSU 按新结构布局写入。旧内核分支临时空实现消除了这类非法结构访问风险，**但尚未解决 Manager 的 reboot 通信路径和 Seccomp 限制**。
2. Module namespace：为 Linux 4.19 不具备的 MODULE_IMPORT_NS 宏加入条件编译保护。
3. 自动装配：源码 pin 到完整 Git SHA，符号链接官方 KernelSU、接入 Kconfig/Kbuild、追加 umi 构建配置。
4. 静态检查继续把 SELinux 判为 BLOCK；CI 验证该阻塞不会被误删除。

## 仍需解决：禁止发布 boot.img

### P0：SELinux 策略及 SID 更新

官方 3.3.0 的 selinux_state.policy / policy_mutex 与旧版 ss / policy_rwlock 不兼容。必须审计 rules.c、sepolicy.c 的锁、SID 映射、一致性、AVC 重置及 RCU 生命周期。不能用宏别名、指针强转或直接关闭 SELinux 代替。

### P0：Manager 通信

旧版 Seccomp 不含新版缓存：空函数仅避免非法内存访问，**不代表 Manager 可以在 Zygote 的 Seccomp 下发起 reboot 握手**。需核对 setresuid、匿名 FD、reboot Kprobe 和用户态调用链。

### P0：Kernel Hook / CFI

验证 ksu_syscall_dispatcher 重定向与 ARM64 syscall_trace_enter 调用顺序、32 位兼容路径、CFI、同步卸载及只读页补丁的约束。

### P1：构建工具链

Actions 暂用 Ubuntu 24.04 的 Clang 18 **仅作诊断**。如果内核不兼容，应固定 LineageOS 对应 Clang prebuilts，不应关闭 CFI/LTO 来掩盖错误。

### P1：引导镜像

当前构建脚本只诊断 Image/DTB；即使编译成功也不会自动发布 boot.img。必须对应手机**实际安装的 ROM 构建版本**取得原版 ramdisk、设备树、boot header、分区信息并保留恢复路径。

## 本地命令

```bash
bash scripts/prepare_sources.sh
python3 scripts/apply_compat.py .work/KernelSU
python3 scripts/audit.py .work/kernel .work/KernelSU
bash scripts/build_kernel.sh baseline
# 仅用于收集错误；不可刷机
bash scripts/build_kernel.sh ksu
```

`audit.py` 当前因 SELinux 风险返回退出码 2，这是预期安全阻塞。GitHub Actions 的绿色检查不等于真机已验证。

**新增门禁：** 即使 SELinux 适配完成，Manager 握手仍列为独立 `manager-handshake` BLOCK，不能仅因 Seccomp 未越界就认为 Root 授权功能可用。

## 2026-10-14：首轮内核诊断编译修复

- CI #38529605474：原版基线失败于 `llvm-ar: not found`，两路编译出现 `llvm-nm: not found`。构建脚本现在把 Ubuntu LLVM 18 二进制目录加进 PATH，并预检查实际可执行文件。
- 同轮 KernelSU 编译暴露了 `file_wrapper.c` 在 Linux 4.19 不支持的 `iopoll`、`remap_file_range` 和 `REMAP_FILE_DEDUP`。
- 新增 `scripts/patch_vfs_419.py`，原生采用 `clone_file_range` / `dedupe_file_range`，在不修改新版分支语义的前提下修复旧 VFS 接口。
- 新增 VFS 适配检查、单元测试及单对象编译步骤；还没有验证全量构建成功。
- SELinux 和 Manager/Seccomp 的 P0 安全阻塞仍在，绝不发布未经验证的 boot.img。

## 2026-10-14：第二轮 KernelSU 驱动编译诊断

- 快速 CI #38533421758：工具链路径及 VFS 原有报错不再出现。新增三处阻塞：`flask.h` 未在子目录编译前生成；旧内核缺少 `uapi/linux/mount.h`；`fsnotify_ops` 从旧版 `handle_event` 演进为新版 `handle_inode_event`。
- 先编译 `security/selinux/flask.h`，使 Kbuild 生成相应头文件，再单独构建 KernelSU。
- 新增 `patch_legacy_apis.py`，为 4.19 提供保持旧回调原型的 fsnotify 桥接；使用 `do_mount()`（旧版 API）替代不存在的 `path_mount()`。
- 旧内核 `do_mount` 读取用户地址，本补丁仅在该调用期间将当前任务地址限制临时切换到 KERNEL_DS，并明确无条件恢复。此方案仅限 4.19 实验使用，仍需真机安全验证。
- SELinux 策略布局、Manager/Seccomp 与内核 Hook 的 P0 不变，**禁止发布 boot.img**。

## 2026-10-14：第三轮 KernelSU 快速编译诊断

- CI #38534591389：SELinux 生成头文件、VFS、Mount、fsnotify 已进入正常编译；随后遇到 `struct seccomp.filter_count` 不存在、`TWA_RESUME` 新版枚举不兼容，以及 `put_task_struct` 头文件缺失。
- `patch_policy_419.py` 只对 Linux 4.19 使用 `put_seccomp_filter(fake)` 和旧版 `task_work_add(..., true)`，避免访问不存在的 seccomp 成员；额外包含旧版 `sched/task.h`。
- 这是兼容性编译修复，**不等于 Seccomp/Manager 握手通过**；Root 授权安全门禁保持。

## 2026-10-14：SELinux 4.19 核心阻塞（最新快速 CI #38535181738）

- 之前的 LLVM、VFS、mount、fsnotify、seccomp/task_work 编译报错已不再出现，快速 Kbuild 进入 SELinux C 文件编译。
- Sulog `linux/minmax.h` 在旧内核不存在：引入单独的 `patch_sulog_419.py`，仅在 4.19 使用 `linux/kernel.h`。
- 不允许将旧版 `struct avtab.htable` （`struct flex_array *`）当作新版 `struct avtab_node **` 使用；不允许将旧版 `filename_trans` 当作新版 `filename_trans_key`。
- 旧版 `struct selinux_ss` 是 `policy_rwlock + policydb + sidtab`，新版 `struct selinux_policy` 的 `policy_mutex + RCU 指针整体替换` 不是等价接口。下一阶段需要设计可验证的安全策略复制和原子发布方案。
- CI 快速编译现在附带精简的 Clang 错误摘要，完整日志仍保留在 Artifact。
- 原版 LineageOS 的全量内核诊断编译已经在 CI #38533020110 单独通过。**这不构成可刷机、KernelSU 驱动成功或真机通过的证明。**

## 2026-10-14：4.19 SELinux 原生事务接口核实

- 已确认 `security_read_policy()` 在 `policy_rwlock` 读锁下序列化原始策略。
- `security_load_policy()` 对完整策略执行 SID 转换、在写锁下发布，以及 AVC 清空、状态通知。
- 优先使用旧内核自己的事务原语而不是仿造新版 `selinux_state.policy` 指针替换。
- 引入源码能力检查 `inspect_selinux_419.py` 和单元测试；它不解除 `selinux-abi` 阻塞，详情见 `docs/SELINUX_419_PORT.md`。

## 2026-10-14：Supercall Task API 补丁

- CI #38537057082 在 SELinux 报错之外，还暴露 supercall/dispatch.c 的 tasklist_lock、init_task、task_pgrp、task_session 未声明。
- Linux 4.19 的声明分别由 sched/task.h 与 sched/signal.h 提供；新增带严格源码匹配与单元测试的补丁，不触碰权限判断逻辑。

## 2026-10-14：旧版 SELinux policydb 具体移植第一步

- CI #38537745526：Supercall 任务管理错误已消失；失败点集中在 SELinux 的 `avtab`、`filename_trans`、`type_attr_map` 和 `rules.c`。
- 增加严格上游匹配的 `patch_avtab_419.py`：旧内核 avtab 的桶头属于 `flex_array`，通过 `flex_array_get_ptr` / `flex_array_put_ptr` 操作；删除节点使用旧内核 `avtab_destroy` 维护私有 slab 对象生命周期，而非 `kfree`。
- 增加 `patch_filename_419.py`：在 Linux 4.19 分支使用包含 `stype` 的 `struct filename_trans`，配合旧版 `struct hashtab *` 和 `filename_trans_ttypes` 进行增改。
- 两个补丁均保持新内核分支的官方实现不变，均提供幂等性和上游版本变化拒绝测试。
- 当前仍未解决 `add_type` 的 `flex_array` 扩容、SELinux 安全策略发布和旧版 SID 转换，`selinux-abi` 与 `manager-handshake` BLOCK 不得取消。CI 成功不等于真机可用。

## 2026-10-14：SELinux 4.19 Type/Attribute 兼容编译

- CI #38539924974：先前的 avtab 和 filename_trans 编译错误已清零；剩余大量编译错误为 `add_type` 和 `rules.c` 现代策略发布。
- 新增 `patch_type_419.py`，通过旧内核 `flex_array_alloc`、`flex_array_prealloc`、`flex_array_get/put` 构建 type->attribute、自定义 type->datum 和 type->name 映射。
- 所有新数组分配、复制和新条目初始化成功后才替换旧容器；错误时释放新数组及新条目的 bitmap，避免直接将旧版 flex_array 转成指针数组。
- 旧版属性取值也改为 `flex_array_get`，并防御空指针；不改变新内核实现分支。
- **仅解决静态编译兼容，尚需验证 type 更新的并发、role 扩展失败和策略序列化长度。** 保留 P0 阻塞。

## 2026-10-14：Policydb 编译门禁验证结果

- 静态及 Python 回归测试：CI #38540529077 **通过**。
- Linux 4.19 KernelSU 驱动编译：CI #38540529074 **失败**，但 C 编译已穿过 avtab、filename_trans、type 与 attribute 的适配代码，原先四类编译错误不再出现。
- 最新编译阻塞只集中在 `selinux/rules.c` 和 `selinux/sepolicy.c` 的新版 `struct selinux_policy`、`selinux_state.policy`、`policy_mutex` 机制。
- 下一阶段必须以原生 `security_read_policy` / `security_load_policy` 设计受控事务，并验证失败回滚、长度增长、SID 转换、AVC 更新、SELinux 并行加载和 backup_sepolicy/selinux_hide 的兼容性。**不得用字段别名、强转或禁用 SELinux 假装完成适配。**
- P0 发布门禁仍为 `selinux-abi` 与 `manager-handshake`。当前不允许制作可供刷写的 boot.img。

## 2026-10-14：首版 SELinux 4.19 原生事务移植（实验）

- 新增 `patch_selinux_core_419.py`，在旧版 LineageOS 的 `security/selinux/ss/services.c` 引入 `ksu_legacy_policy_transaction`，系统与 KernelSU 的 `security_load_policy` 路径共用互斥锁。
- 事务先通过内核 `security_read_policy` 读取独立快照，对独立 `policydb` 修改并经过有界 `policydb_write` 序列化后，才调用原生加载流程发布。失败路径保持活动策略不变。
- `patch_rules_419.py` 为 4.19 添加官方默认规则及批量 `sepolicy` 命令对应的独立事务编辑回调，保留新版 KernelSU 分支行为。
- 旧内核没有与现代 `backup_sepolicy` 等价的 SID 备份，因此 4.19 的 SELinux Hide 功能暂不注册；将来必须重新设计，而不能创建伪造结构。
- **尚未通过真实内核编译及设备测试**；默认规则异常处理、系统重载竞争、策略类型扩容、selinuxfs 节点更新与 Manager 连接均需验证。CI 保持 `selinux-abi` 和 `manager-handshake` 为 BLOCK，不可生成可刷写镜像。

## 2026-10-14：完整内核产物验收与 Manager 源码风险检查

- 官方 KernelSU 3.3.0 的完整驱动目录构建已在 #38549163434 与 #38549614511 成功；完整内核 Image/DTB 链接尚以独立任务验证，成功以前不作结论。
- `check_build_output.py` 会在正常整核构建结束后核实最终 CONFIG_KSU/KPROBES/SELINUX/EXT4 配置、vmlinux、Image、设备树与驱动归档；此检查**不生产或发布 boot.img**。
- `inspect_manager_419.py` 基于锁定内核源码确认 `secure_computing()` 发生在 `trace_sys_enter()` 之前；旧 4.19 Seccomp 无 action_cache，因此 Manager reboot 通道未解决。虽存在由 `setresuid` 注入匿名 FD 的另一实现，但必须验证 Android 16 Manager 实际进程生命周期。
- 完整链接成功仍不得解除 `selinux-abi`、`manager-handshake` 两个发布阻塞；SELinux/AVC 更新与 Root 授权需要 Enforcing 真机测试。

## 2026-10-14：整核链接首次失败及修复

- 真实完整 KernelSU 内核链接 CI #38549614526：驱动与其它子系统已完成 LTO vmlinux.o、MODPOST，最终链接只遇到一处 `ld.lld-18: undefined symbol: path_umount`，引用来自 `feature/kernel_umount.c:71`。
- Linux 4.19 的 `do_umount` 是 `fs/namespace.c` 私有函数，不能简单声明 `extern path_umount` 或用不安全的符号强转修复。
- 新增 `patch_umount_419.py`：在内核自己的 `fs/namespace.c` 中增加条件编译的 `ksu_legacy_path_umount`，复用 `ksys_umount` 的原生参数校验、mount capability、命名空间与 MNT_LOCKED 检查，并用 `dput`/`mntput_no_expire` 按 4.19 语义消费传入的路径引用。
- 同时让 KernelSU 的旧版分支引用此辅助函数，其他内核路径不变。加入源码精确匹配单测与静态链接风险审查。
- 自动完整构建改为仅验证 KernelSU，原版对照编译保留在手动 workflow_dispatch 中以避免每次重复耗费 CI 时间。
- **链接仍需新 CI 验证，SELinux Enforcing、Manager 和真机 root 功能仍有 P0 阻塞，禁止刷机。**

## 2026-10-14：整核通过后的安全回归

- #38552038273 完成官方 KernelSU 3.3.0 与 umi Linux 4.19 的完整 vmlinux/ Image 链接，原生产物检查为 passed=true。
- 旧版批量 SELinux 命令改为**任意命令失败均取消整批事务**，不得发布已部分修改的 policydb。
- 增强产物检查：必须包含 umi-sm8250-overlay.dtbo；记录 Image 与 umi DTBO 的 SHA-256 清单。
- 尚未进行真机 SELinux Enforcing、Root/Manager 握手、boot.img 封装；安全阻塞继续保留。

## 2026-10-14：真实 Xiaomi Mi 10 umi 非 A/B 分区布局已确认

- 真机只读报告：`umi` / Android 16（API 36）/ LineageOS `23.2-20261004-NIGHTLY-umi` / `4.19.325-cip131-st15-perf-g71b13e62f057` / SELinux `Enforcing`。
- `ro.build.ab_update=false`，`ro.boot.slot` 和 `ro.boot.slot_suffix` 为空，且只读查看到独立的 `boot`、`recovery`、`dtbo`、`vbmeta`，无 A/B 槽位后缀：据此确认非 A/B、独立 Recovery 布局。
- 上游 `sm8250-common/BoardConfigCommon.mk` 非 Virtual A/B 分支预期 Boot Header v2、page size 4096、DTB 纳入 boot image、DTBO 独立，**仍需验证现有原版 boot.img 头及实际分区容量**。
- `config/umi_preflight_20261014.json` 只保存无个人标识的观测信息；`scripts/check_umi_preflight.py` 与回归测试保证固定源码匹配、拒绝误用 A/B 配置，并始终报告 `safe_to_flash=false`。
- CI #38555215723 已通过完整内核链接和 umi DTBO 验收；但并未生成可刷写镜像，也尚未验证 SELinux 策略运行时可靠性与 Manager 握手，两项继续 BLOCK。

## 2026-10-14：真机首次启动失败（必须阻止重复刷入）

- 用户在小米 10 umi / LineageOS 23.2-20261004 上刷入通过 CI #38567509103 结构验收的实验 `boot.img`，**开机失败**；随后刷回同版本原版 `boot.img`，已恢复正常启动。
- 失败镜像 SHA-256：`b5701bb8347ea4d37c584b96eedd00f6e51d867aa9a68ec21d75a16f85ae2aaf`（CI #38567509103，Git commit dbad536）。**标记为 KNOWN_BOOT_FAILURE，禁止重复刷写。** CI 结构校验不等于真机可启动。
- 失败阶段（黑屏、Logo、bootanimation、Recovery/fastboot）、内核 panic/ramoops/pstore 日志：**尚无实机证据**，不得擅自归因 SELinux 或 KernelSU。
- 下一步：只读收集残存 pstore/bootreason；从原版 Image 的 IKCONFIG 比对 Clang18 编译的 KernelSU .config，先完成干净的非 KSU 基线兼容验证，再隔离早期 Hook、SELinux 策略事务等因素。任何新调试版也不等于稳定或安全。
