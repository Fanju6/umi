# Umi / KernelSU v3.3.1 首次 Manager FD Bootstrap 原型（禁止真机部署）

## 为什么做这个试验

在 v3.3.0 已验证的 TEST2 中，第一次打开 Manager 失败，用户必须通过 Rooted debugging 安装 /data/adb/ksud；之后 Root/管理器自动重装都正常。

v3.3.1 上游代码确认：Manager 启动 libksud.so debug su 时尝试扫描已继承的 anon_inode:[ksu_driver] 描述符；缺失则通过特殊 reboot syscall 请求新 FD。KernelSU 在 zygote setresuid 时给 Manager 安装的 FD 带 O_CLOEXEC，不能直接跨 exec 传给 libksud.so。Linux 4.19 缺少新版 Seccomp action cache，特殊 reboot 路径可能在 Secure Computing 阶段被过滤。此处**属于源码支持的高可信假设，但尚非首次失败时的 SIGSYS 日志证据**。

## 实验补丁

在 Linux 4.19 下使用 sched_process_exec Tracepoint，在 exec 完成且内核已执行 do_close_on_exec 之后，仅对：
- 当前进程 uid 为经过 KernelSU 管理器 APK 验证的 is_manager()
- 被执行文件属于 /data/app/ 的 me.weishu.kernelsu- 管理器私有目录
- 被执行 ELF 文件名严格为 libksud.so

调用现有官方 ksu_install_fd()，该函数仍使用 O_CLOEXEC，在下一次 exec 时自动关闭新 FD。普通应用、其它可执行文件、其它内核版本不受影响；无 SELinux 放行、无 Seccomp 绕过、无任意 UID Root 授权。本试验不修改用户态官方 KernelSU 3.3.1 源码。

**风险：**新增进程执行跟踪和 FD 注入时机可能与 Android 16 / Linux 4.19 内核的执行安全锁、SELinux 和 KSU 生命周期产生交互；不能只靠静态编译验证并宣称安全。此补丁在独立实验分支，不加入正式迁移 PR，禁止打包、刷写或发布真机镜像。只有全量编译、针对性安全审查和独立可恢复设备真机首次 Root 测试通过后，才能考虑正式纳入产品。

## 静态验收

- 代码针对 KernelSU 固定 v3.3.1 supercall.c 使用严格源码锚点；改变上游结构立即拒绝。
- 只在版本小于 5.0 的旧内核启用，tracepoint 注册成功才记录，并在退出阶段有对称注销。
- 编译失败应阻塞合并。此原型不能用于此前已经稳定运行的 TEST2 核心。


## 2026-10-15：Tracepoint 执行上下文修复

查阅固定 umi Linux 4.19 源码（include/linux/tracepoint.h 的 __DO_TRACE），探针回调执行时 preempt_disable_notrace()，所以**原型直接在探针内 ksu_install_fd() 不安全**：它会经 kzalloc(GFP_KERNEL)、anon_inode_getfile 等路径分配内存，可能在非可睡眠上下文中调度。

原型现改为：探针只验证已经由 KernelSU 签名登记的 Manager appid 与 /data/app/.../me.weishu.kernelsu-.../lib/arm64/libksud.so 路径，以 GFP_ATOMIC 分配少量任务对象，然后 task_work_add(current, cb, true) 通知 resume；在进程返回用户空间前的 task_work 回调中重验 is_manager() 和 PF_EXITING，才执行原版 ksu_install_fd()。队列添加失败时释放对象并保留正常内核路径；仍然使用 CLOEXEC FD，不触碰安全策略，也不宣称自动安装成功。

**仍待验证：**真实 Android 安装路径是否完全匹配、task_work 调度及对象生命周期、匿名 FD 到 Manager CLI 的 ioctl 授权、与 KSU 内核其他 task_work 顺序及 SELinux 的交互。编译、源码测试不能替代真机。必须维持 Draft，不合并入 TEST2。
