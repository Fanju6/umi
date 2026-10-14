# Linux 4.19 SELinux 事务式移植方案

目标：LineageOS 23.2 umi 的 Linux 4.19 及官方 KernelSU v3.3.0（不是 KernelSU Next）。

## 已发现的原生 API

- security_read_policy(state, &data, &len)：通过 policy_rwlock 的读锁序列化活动策略。
- security_load_policy(state, data, len)：在旧内核中解析策略、转换 SID、保护性更新 policydb 与 sidtab、使 AVC 缓存失效。
- 以上源码位于 LineageOS android_kernel_xiaomi_sm8250 的 security/selinux/ss/services.c。
- 旧内核数据结构为 selinux_state.ss / struct selinux_ss / policy_rwlock。
- 官方 KernelSU 3.3.0 使用 selinux_state.policy / policy_mutex / struct selinux_policy；这些不是兼容数据结构。

## 待实现的路线

1. 使用 security_read_policy 获取策略快照，按旧版 policydb_read 在独立内存中解析、修改；所有失败路径释放缓冲区。
2. 使用真实的 4.19 flex_array 访问 avtab、type 属性和名称表，禁止将其直接当成新版原生指针数组。
3. 适配旧版 filename_trans/filename_trans_ttypes 的表示形式，保证重复规则与内存管理正确。
4. 修改后完整序列化、校验长度，并通过旧内核 security_load_policy 执行原生策略提交和 SID/AVC 更新。
5. 审计并行 policy reload 与安全上下文竞争，不能仅因为有 API 就直接绕过 selinuxfs 中的同步机制。
6. 解决 backup_sepolicy 与 feature/selinux_hide.c 所依赖的新版独立策略 SID 转换机制。
7. 完整编译成功之后，在 SELinux Enforcing、root 授权、模块挂载、OOM、策略更新和启动恢复等情形下做真机验证。

## 禁止的捷径

- 关闭 SELinux 或切换 Permissive。
- 强转旧内核结构以模仿新版字段，或用宏别名覆盖锁和指针生命周期。
- 未验证策略发布的情况下移除 selinux-abi 安全阻塞。
- 用编译通过冒充设备已经可以刷机。

现阶段仍保留 selinux-abi 与 manager-handshake 两项安全阻塞。