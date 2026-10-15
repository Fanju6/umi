#!/usr/bin/env python3
"""Experimental, narrowly scoped post-exec Manager FD bootstrap for umi Linux 4.19.

This is an opt-in source patch on an ISOLATED EXPERIMENT branch, not a proven
fix. It does not change Seccomp policy, KernelSU authorization, or SELinux.
"""
import argparse
from pathlib import Path

MARKER = "UMI_KSU_419_MANAGER_POSTEXEC_FD_PROTOTYPE"

OLD_INCLUDE = '#include "supercall/internal.h"'
NEW_INCLUDE = """#include "supercall/internal.h"
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 0, 0)
/* UMI_KSU_419_MANAGER_POSTEXEC_FD_PROTOTYPE */
#include <linux/binfmts.h>
#include <linux/sched.h>
#include <linux/string.h>
#include <trace/events/sched.h>
#include "manager/manager_identity.h"
#endif"""

OLD_INIT = """void __init ksu_supercalls_init(void)
{
    int rc;

    ksu_supercall_dump_commands();"""
NEW_INIT = """#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 0, 0)
/*
 * EXPERIMENT ONLY, for official Manager's bundled libksud.so:
 * sched_process_exec fires AFTER do_close_on_exec() in umi fs/exec.c.
 * A new CLOEXEC driver FD created here is therefore visible to this one
 * ksud process; other apps and Manager child processes are not modified.
 * Manager UID is validated against the APK-signature-crowned KSU identity.
 * Never expose a non-CLOEXEC FD from the parent or bypass Seccomp.
 */
static bool umi_manager_fd_trace_registered;

static void umi_manager_ksud_post_exec(void *data, struct task_struct *task,
                                       pid_t old_pid, struct linux_binprm *bprm)
{
    const char *filename;
    const char *basename;
    int fd;

    if (task != current || !is_manager() || !bprm)
        return;
    filename = bprm->filename;
    if (!filename || strncmp(filename, "/data/app/", 10))
        return;
    if (!strstr(filename, "/me.weishu.kernelsu-"))
        return;
    basename = strrchr(filename, '/');
    if (!basename || strcmp(basename, "/libksud.so"))
        return;
    fd = ksu_install_fd();
    if (fd < 0)
        pr_warn("manager ksud post-exec fd install failed: %d\\n", fd);
    else
        pr_info("manager ksud post-exec driver fd installed\\n");
}
#endif

void __init ksu_supercalls_init(void)
{
    int rc;

#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 0, 0)
    rc = register_trace_sched_process_exec(umi_manager_ksud_post_exec, NULL);
    if (rc)
        pr_err("manager ksud post-exec bootstrap trace registration failed: %d\\n", rc);
    else
        umi_manager_fd_trace_registered = true;
#endif

    ksu_supercall_dump_commands();"""

OLD_EXIT = """void __exit ksu_supercalls_exit(void)
{
    unregister_kprobe(&reboot_kp);"""
NEW_EXIT = """void __exit ksu_supercalls_exit(void)
{
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 0, 0)
    if (umi_manager_fd_trace_registered)
        unregister_trace_sched_process_exec(umi_manager_ksud_post_exec, NULL);
#endif
    unregister_kprobe(&reboot_kp);"""


def patch(path: Path) -> bool:
    ksu = path / "kernel" if (path / "kernel/Kbuild").is_file() else path
    if not (ksu / "Kbuild").exists():
        raise ValueError("Expected official pinned KernelSU checkout")
    target = ksu / "supercall/supercall.c"
    original = target.read_text(encoding="utf-8")
    if MARKER in original:
        if (NEW_INCLUDE not in original or NEW_INIT not in original or
                NEW_EXIT not in original or original.count(MARKER) != 1):
            raise ValueError("Incomplete experimental post-exec patch")
        return False
    for old in (OLD_INCLUDE, OLD_INIT, OLD_EXIT):
        if original.count(old) != 1:
            raise ValueError("Upstream changed, refusing unsafe post-exec FD patch")
    updated = original.replace(OLD_INCLUDE, NEW_INCLUDE, 1)
    updated = updated.replace(OLD_INIT, NEW_INIT, 1)
    updated = updated.replace(OLD_EXIT, NEW_EXIT, 1)
    if target.read_text(encoding="utf-8") != original:
        raise RuntimeError("Target changed during patch")
    target.write_text(updated, encoding="utf-8")
    return True


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("ksu", type=Path)
    args = cli.parse_args()
    print("patched experimental bootstrap" if patch(args.ksu.resolve()) else "already patched")
