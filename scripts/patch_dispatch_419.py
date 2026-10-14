#!/usr/bin/env python3
"""Provide Linux 4.19 task API declarations for official KernelSU dispatch.c."""
import argparse
from pathlib import Path
MARKER="UMI_KSU_419_DISPATCH_TASK_HEADERS"
OLD="#include <linux/thread_info.h>"
NEW="""/* UMI_KSU_419_DISPATCH_TASK_HEADERS */
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 0, 0)
#include <linux/sched/task.h>   /* tasklist_lock, init_task */
#include <linux/sched/signal.h> /* task_pgrp, task_session */
#endif
#include <linux/thread_info.h>"""
def patch(root):
    root = root/"kernel" if (root/"kernel/Kbuild").is_file() else root
    if not (root/"Kbuild").is_file():
        raise ValueError("Not a KernelSU tree")
    file=root/"supercall/dispatch.c"
    original=file.read_text()
    if MARKER in original:
        return False
    if original.count(OLD)!=1 or "task_pgrp(" not in original:
        raise ValueError("Unexpected KernelSU dispatch source")
    file.write_text(original.replace(OLD,NEW,1))
    return True
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("kernelsu",type=Path)
    a=p.parse_args()
    print("4.19 dispatch:", "patched" if patch(a.kernelsu.resolve()) else "already patched")
