#!/usr/bin/env python3
"""Adapt upstream KernelSU v3.3.1 manager task_work to Linux 4.19."""
from pathlib import Path
import argparse

MARKER = "UMI_KSU_419_MANAGER_TASK_WORK"
OLD = """            if (!task_work_add(current, cb, TWA_RESUME))
                return;"""
NEW = """#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 0, 0)
            /* UMI_KSU_419_MANAGER_TASK_WORK: legacy notify=true. */
            if (!task_work_add(current, cb, true))
#else
            if (!task_work_add(current, cb, TWA_RESUME))
#endif
                return;"""


def patch(path: Path) -> bool:
    ksu = path / "kernel" if (path / "kernel/Kbuild").is_file() else path
    if not (ksu / "Kbuild").is_file():
        raise ValueError("Expected pinned KernelSU checkout")
    target = ksu / "manager/pkg_observer.c"
    src = target.read_text(encoding="utf-8")
    if MARKER in src:
        if src.count(MARKER) != 1 or src.count(NEW) != 1:
            raise ValueError("Incomplete previous patch")
        return False
    if (src.count(OLD) != 1 or
            '#include <linux/task_work.h>' not in src or
            '#include <linux/version.h>' not in src or
            'static void ksu_defer_track_throne(void)' not in src or
            'ksu_track_throne_tw_func' not in src):
        raise ValueError("Unknown source revision")
    modified = src.replace(OLD, NEW, 1)
    if target.read_text(encoding="utf-8") != src:
        raise RuntimeError("Source changed")
    target.write_text(modified, encoding="utf-8")
    return True


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("ksu", type=Path)
    a = p.parse_args()
    print("patched" if patch(a.ksu.resolve()) else "already patched")
