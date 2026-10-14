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
