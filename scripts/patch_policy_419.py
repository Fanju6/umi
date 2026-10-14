#!/usr/bin/env python3
"""Reviewable Linux 4.19 policy/task-work adaptations for KernelSU v3.3.0."""
import argparse
from pathlib import Path

MARKER = "UMI_KSU_419_POLICY_COMPAT"

def replace_one(src, old, new, label):
    if src.count(old) != 1:
        raise ValueError("Unexpected upstream in " + label)
    return src.replace(old, new, 1)

def patch(root):
    root = root / "kernel" if (root / "kernel/Kbuild").is_file() else root
    if not (root / "Kbuild").is_file():
        raise ValueError("Not KernelSU kernel")
    profile = root / "policy/app_profile.c"
    allow = root / "policy/allowlist.c"
    supercall = root / "supercall/supercall.c"
    p, a, s = [f.read_text() for f in (profile, allow, supercall)]
    pp, aa, ss = p, a, s
    if MARKER not in p:
        p = replace_one(p,
          "    atomic_set(&current->seccomp.filter_count, 0);",
          """#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 0, 0)
    atomic_set(&current->seccomp.filter_count, 0);
#endif /* UMI_KSU_419_POLICY_COMPAT: field does not exist in 4.19 */""",
          "filter_count")
        p = replace_one(p,
          "    seccomp_filter_release(fake);",
          """#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 0, 0)
    /* 4.19 exports the task-based reference release helper instead. */
    put_seccomp_filter(fake);
#else
    seccomp_filter_release(fake);
#endif""",
          "seccomp release")
    if MARKER not in a:
        a = replace_one(a, "#include <linux/task_work.h>",
                        "/* UMI_KSU_419_POLICY_COMPAT */\n#include <linux/task_work.h>\n#include <linux/sched/task.h>", "task header")
        a = replace_one(a, "    if (task_work_add(tsk, cb, TWA_RESUME)) {",
          """#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 0, 0)
    if (task_work_add(tsk, cb, true)) {
#else
    if (task_work_add(tsk, cb, TWA_RESUME)) {
#endif""", "allowlist task_work")
    if MARKER not in s:
        s = replace_one(s,"#include <linux/task_work.h>",
                        "/* UMI_KSU_419_POLICY_COMPAT */\n#include <linux/task_work.h>", "supercall task header")
        s = replace_one(s, "        if (task_work_add(current, &tw->cb, TWA_RESUME)) {",
          """#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 0, 0)
        if (task_work_add(current, &tw->cb, true)) {
#else
        if (task_work_add(current, &tw->cb, TWA_RESUME)) {
#endif""", "supercall task_work")
    for f,old,new in [(profile,pp,p),(allow,aa,a),(supercall,ss,s)]:
        if f.read_text()!=old:
            raise RuntimeError("Source was modified while preparing patch: "+str(f))
        if new!=old: f.write_text(new)
    return sum(x!=y for x,y in [(p,pp),(a,aa),(s,ss)])

if __name__ == "__main__":
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("kernelsu",type=Path)
    args=a.parse_args()
    print("Patched KernelSU 4.19 policy files:",patch(args.kernelsu.resolve()))
