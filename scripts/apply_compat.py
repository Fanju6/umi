#!/usr/bin/env python3
"""Apply ONLY reviewed, mechanical compatibility shims to pinned official KernelSU.

No unsafe layout casts. The Linux 4.19 SELinux policy port is intentionally NOT
implemented: scripts/audit.py must continue to block before a flashable release.
"""
import argparse
from pathlib import Path

LEGACY_MARKER = "UMI_KSU_419_NO_ACTION_CACHE"
NAMESPACE_MARKER = "UMI_KSU_419_NAMESPACE_GUARD"

# On Linux 4.19, seccomp_filter has no action_cache. The cache operations must
# not dereference the newer structure. This avoids a memory corruption bug;
# it is NOT proof that KernelSU manager's reboot handshake will function.
LEGACY_GUARD = """/* UMI_KSU_419_NO_ACTION_CACHE: legacy seccomp has no action_cache. */
#include <linux/version.h>
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 9, 0)
#include <linux/seccomp.h>
void ksu_seccomp_clear_cache(struct seccomp_filter *filter, int nr)
{
    (void)filter;
    (void)nr;
}
void ksu_seccomp_allow_cache(struct seccomp_filter *filter, int nr)
{
    (void)filter;
    (void)nr;
}
#else
"""

IMPORT_OLD = """#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 13, 0)
MODULE_IMPORT_NS("VFS_internal_I_am_really_a_filesystem_and_am_NOT_a_driver");
#else
MODULE_IMPORT_NS(VFS_internal_I_am_really_a_filesystem_and_am_NOT_a_driver);
#endif"""

IMPORT_NEW = """/* UMI_KSU_419_NAMESPACE_GUARD: macro absent on Linux 4.19. */
#ifdef MODULE_IMPORT_NS
""" + IMPORT_OLD + """
#endif"""


def apply(ksu: Path) -> list[str]:
    root = ksu / "kernel" if (ksu / "kernel" / "Kbuild").is_file() else ksu
    if not (root / "Kbuild").is_file():
        raise ValueError("参数必须是官方 KernelSU 根目录或其 kernel/ 目录")

    changes = []
    sec_file = root / "infra/seccomp_cache.c"
    sec_text = sec_file.read_text(encoding="utf-8")
    if LEGACY_MARKER not in sec_text:
        if ("filter->cache.allow_native" not in sec_text or
                "void ksu_seccomp_allow_cache" not in sec_text):
            raise ValueError("上游 seccomp 源码与锁定版本不符，禁止套用补丁")
        sec_file.write_text(LEGACY_GUARD + sec_text + "\n#endif /* legacy seccomp */\n", encoding="utf-8")
        changes.append("4.19 seccomp no-cache guard")

    init_file = root / "core/init.c"
    init = init_file.read_text(encoding="utf-8")
    if NAMESPACE_MARKER not in init:
        if init.count(IMPORT_OLD) != 1:
            raise ValueError("上游 MODULE_IMPORT_NS 代码发生变化，禁止猜测替换")
        init_file.write_text(init.replace(IMPORT_OLD, IMPORT_NEW), encoding="utf-8")
        changes.append("module namespace macro guard")

    return changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ksu", type=Path, help="KernelSU directory")
    args = parser.parse_args()
    for name in apply(args.ksu.resolve()):
        print("[FIX]", name)
    print("[INFO] SELinux 4.19 port remains blocked")


if __name__ == "__main__":
    main()
