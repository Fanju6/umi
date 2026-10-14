#!/usr/bin/env python3
"""Static pre-build checks. This is NOT a compiler or boot test."""
import argparse
import json
import re
import sys
from pathlib import Path


def read(root: Path, name: str) -> str:
    path = root / name
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def inspect(kernel: Path, ksu_repo: Path) -> list[dict]:
    ksu = ksu_repo / "kernel" if (ksu_repo / "kernel/Kbuild").is_file() else ksu_repo
    if not (kernel / "Makefile").is_file() or not (ksu / "Kbuild").is_file():
        raise ValueError("请提供完整的 LineageOS 内核源码和官方 KernelSU 源码")
    result = []

    def add(key: str, status: str, detail: str):
        result.append(dict(key=key, status=status, detail=detail))

    mk = read(kernel, "Makefile")
    add("kernel-version", "PASS" if re.search(r"^VERSION = 4\nPATCHLEVEL = 19$", mk, re.M) else "BLOCK",
        "本项目仅审查 Linux 4.19 内核")
    add("ksu-wiring", "PASS" if
        'source "drivers/kernelsu/Kconfig"' in read(kernel, "drivers/Kconfig") and
        'obj-$(CONFIG_KSU) += kernelsu/' in read(kernel, "drivers/Makefile")
        else "BLOCK", "KernelSU Kbuild/Kconfig 已正确接线")
    add("umi-config", "PASS" if "CONFIG_KSU=y" in read(
        kernel, "arch/arm64/configs/vendor/xiaomi/umi.config") else "BLOCK",
        "umi 配置片段包含 CONFIG_KSU=y；仍须核对最终生成的 .config")
    apis = [
        ("syscall-table", "sys_call_table" in read(kernel, "arch/arm64/kernel/sys.c")),
        ("trace-enter", "TRACE_EVENT_FN(sys_enter" in read(kernel, "include/trace/events/syscalls.h")),
        ("trace-priority", "register_trace_prio_##name" in read(kernel, "include/linux/tracepoint.h")),
        ("nofault-write", "copy_to_kernel_nofault" in read(kernel, "include/linux/uaccess.h")),
    ]
    for key, found in apis:
        add(key, "PASS" if found else "BLOCK", "基础接口" + ("存在" if found else "不存在"))

    sec = read(kernel, "kernel/seccomp.c")
    ksec = read(ksu, "infra/seccomp_cache.c")
    if "struct seccomp_filter" not in sec:
        add("seccomp", "BLOCK", "无法确认 seccomp_filter 原生布局")
    elif "struct action_cache cache;" not in sec and (
            "UMI_KSU_419_NO_ACTION_CACHE" in ksec and
            "LINUX_VERSION_CODE < KERNEL_VERSION(5, 9, 0)" in ksec):
        add("seccomp", "WARN", "已防止直接访问不存在的 action_cache；管理器通信仍需真机验证")
        add("manager-handshake", "BLOCK", "Linux 4.19 缺少 action_cache，未验证在 Seccomp 下获取 Manager FD 的可靠方法；禁止发布")
    elif "struct action_cache cache;" not in sec and "filter->cache.allow_native" in ksec:
        add("seccomp", "BLOCK", "旧版 seccomp_filter 缺少 action_cache；直接访问不安全")
    else:
        add("seccomp", "WARN", "需检查原生 seccomp 机制")

    # Linux 4.19 exposes clone and dedupe file callbacks separately.
    vfs = read(ksu, "infra/file_wrapper.c")
    if ("int (*clone_file_range)" in read(kernel, "include/linux/fs.h") and
            "UMI_KSU_419_VFS_COMPAT" in vfs and
            "p->ops.dedupe_file_range" in vfs and
            "p->ops.clone_file_range" in vfs):
        add("vfs-compat", "WARN", "4.19 克隆/去重回调已有代码适配；仍需编译和运行验证")
    else:
        add("vfs-compat", "BLOCK", "未确认 Linux 4.19 的 VFS file_operations 兼容分支")

    # Old fsnotify callback signatures are ABI-incompatible with 3.3.0.
    observer = read(ksu, "manager/pkg_observer.c")
    mount = read(ksu, "infra/su_mount_ns.c")
    if "UMI_KSU_419_FSNOTIFY_COMPAT" in observer and ".handle_event = ksu_handle_event" in observer:
        add("fsnotify-compat", "WARN", "旧版 handle_event 已独立适配；待编译及真机验证")
    else:
        add("fsnotify-compat", "BLOCK", "4.19 fsnotify_ops 缺少现代 handle_inode_event")
    if "UMI_KSU_419_MOUNT_COMPAT" in mount and "set_fs(old_fs)" in mount:
        add("mount-compat", "WARN", "4.19 do_mount 已适配，恢复旧地址空间限制；待运行验证")
    else:
        add("mount-compat", "BLOCK", "4.19 缺少新版 path_mount 调用接口")

    # Confirm that legacy policydb representation is used, not pointer casts.
    ksepolicy = read(ksu, "selinux/sepolicy.c")
    if ("UMI_KSU_419_AVTAB_FLEX_ARRAY" in ksepolicy and
            "UMI_KSU_419_FILENAME_TRANS" in ksepolicy and
            "UMI_KSU_419_TYPE_FLEX_ARRAY" in ksepolicy and
            "flex_array_get_ptr(db->te_avtab.htable" in ksepolicy and
            "hashtab_search(db->filename_trans" in ksepolicy):
        add("selinux-policydb-419", "WARN",
            "avtab、filename_trans、type 映射添加独立 4.19 分支；仍需策略发布与生命周期验证")
    else:
        add("selinux-policydb-419", "BLOCK",
            "没有找到旧版 avtab、filename_trans 与 type flex_array 兼容实现")

    # The legacy branch is not a modern selinux_policy pointer alias.
    core = read(kernel, "security/selinux/ss/services.c")
    rules = read(ksu, "selinux/rules.c")
    hide = read(ksu, "feature/selinux_hide.c")
    if ("UMI_KSU_419_SELINUX_TXN" in core and
            "ksu_legacy_policy_transaction" in rules and
            "UMI_KSU_419_HIDE_UNSUPPORTED" in hide):
        add("legacy-policy-txn", "WARN",
            "4.19 使用原生策略快照/更新事务；尚未验证真机、并发和全部回滚路径")
        add("legacy-selinux-hide", "WARN",
            "旧内核缺少独立 policy/SID 备份接口，显式禁止 SELinux Hide 功能")
    else:
        add("legacy-policy-txn", "BLOCK", "缺少已审查的 SELinux 4.19 事务适配")
    selinux = read(kernel, "security/selinux/include/security.h")
    krules = read(ksu, "selinux/rules.c")
    if ("struct selinux_ss *ss;" in selinux and "selinux_state.policy" in krules
            and "selinux_state.policy_mutex" in krules):
        add("selinux-abi", "BLOCK",
            "官方新版 policy/policy_mutex 与 umi 旧版 ss/policy_rwlock 不兼容；禁止刷写")
    else:
        add("selinux-abi", "WARN", "旧版 policydb、sidtab、AVC 一致性必须专门验证")

    if "CONFIG_CFI_CLANG=y" in read(kernel, "arch/arm64/configs/vendor/kona-perf_defconfig"):
        add("cfi", "WARN", "Clang CFI 已启用：需验证 Hook 函数调用与内存修改")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("kernel", type=Path)
    p.add_argument("ksu", type=Path)
    p.add_argument("--expect-blocked", nargs="*", default=None,
                   help="仅供 CI 回归测试：期望仍存在的已知 BLOCK 项")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    try:
        checks = inspect(args.kernel.resolve(), args.ksu.resolve())
    except ValueError as exc:
        p.error(str(exc))
    blocked = sorted(c["key"] for c in checks if c["status"] == "BLOCK")
    result = {"status": "BLOCKED" if blocked else "STATIC_ONLY",
              "checks": checks, "blocked": blocked,
              "warning": "即使静态审查通过，也不等于编译通过或可以刷机。"}
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else
          "\n".join(f"[{x['status']}] {x['key']}: {x['detail']}" for x in checks) +
          "\nRESULT: " + result["status"])
    if args.expect_blocked is not None:
        expected = sorted(args.expect_blocked)
        if blocked != expected:
            print(f"期望 BLOCK {expected}，实际 BLOCK {blocked}", file=sys.stderr)
            return 2
        return 0
    return 2 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
