#!/usr/bin/env python3
"""Port KernelSU path_umount to umi Linux 4.19's native mount cleanup API.

The 4.19 do_umount() is file-local in fs/namespace.c. Add a narrowly scoped
helper there to reuse *exactly* the old ksys_umount capability, namespace,
MNT_LOCKED and reference-release semantics. Do not use set_fs to reinterpret
kernel pathname buffers as userspace pointers.
"""
from pathlib import Path
import argparse

MARKER = "UMI_KSU_419_PATH_UMOUNT"
INCLUDE = "#include <linux/sched.h>"
DECLARATION = "extern int path_umount(struct path *path, int flags);"
ANCHOR = "SYSCALL_DEFINE2(umount, char __user *, name, int, flags)"
HELPER = r"""/* UMI_KSU_419_PATH_UMOUNT: path-based umount for the KernelSU builtin. */
#ifdef CONFIG_KSU
int ksu_legacy_path_umount(struct path *path, int flags)
{
    struct mount *mnt;
    int ret;

    if (!path || !path->mnt || !path->dentry)
        return -EINVAL;

    mnt = real_mount(path->mnt);
    ret = -EINVAL;
    if (flags & ~(MNT_FORCE | MNT_DETACH | MNT_EXPIRE | UMOUNT_NOFOLLOW))
        goto out;
    ret = -EPERM;
    if (!may_mount())
        goto out;
    ret = -EINVAL;
    if (path->dentry != path->mnt->mnt_root)
        goto out;
    if (!check_mnt(mnt))
        goto out;
    if (mnt->mnt.mnt_flags & MNT_LOCKED)
        goto out;
    ret = -EPERM;
    if (flags & MNT_FORCE && !capable(CAP_SYS_ADMIN))
        goto out;

    ret = do_umount(mnt, flags);
out:
    /*
     * Match ksys_umount's path cleanup, not path_put(): the latter changes
     * mnt_expiry_mark and breaks MNT_EXPIRE semantics. This function consumes
     * the path reference obtained by kern_path() exactly once.
     */
    dput(path->dentry);
    mntput_no_expire(mnt);
    return ret;
}
#endif /* CONFIG_KSU */

"""
DECL_NEW = """/* UMI_KSU_419_PATH_UMOUNT: Linux 4.19 kernel-side helper. */
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 9, 0)
extern int ksu_legacy_path_umount(struct path *path, int flags);
#define path_umount ksu_legacy_path_umount
#else
extern int path_umount(struct path *path, int flags);
#endif"""

def patch(kernel: Path, kernelsu: Path) -> bool:
    root = kernelsu / "kernel" if (kernelsu / "kernel/Kbuild").is_file() else kernelsu
    if not (root / "Kbuild").is_file():
        raise ValueError("Expected official KernelSU checkout")
    ns = kernel / "fs/namespace.c"
    umount = root / "feature/kernel_umount.c"
    nsrc, usrc = ns.read_text(), umount.read_text()
    if MARKER in nsrc and MARKER in usrc:
        return False
    if MARKER in nsrc or MARKER in usrc:
        raise ValueError("Partial 4.19 umount patch, refusing to continue")
    if nsrc.count(ANCHOR) != 1 or usrc.count(DECLARATION) != 1 or usrc.count(INCLUDE) != 1:
        raise ValueError("Upstream mount interface changed")
    # Deny patch if stock helper semantics diverged from expected Lineage 4.19.
    expected = ("static int do_umount(struct mount *mnt, int flags)",
                "static inline bool may_mount(void)",
                "if (!check_mnt(mnt))",
                "mntput_no_expire(mnt);",
                "retval = do_umount(mnt, flags);")
    if any(symbol not in nsrc for symbol in expected):
        raise ValueError("Unable to verify native 4.19 umount semantics")
    new_ns = nsrc.replace(ANCHOR, HELPER + ANCHOR, 1)
    new_umount = usrc.replace(INCLUDE, "#include <linux/version.h>\n" + INCLUDE, 1)
    new_umount = new_umount.replace(DECLARATION, DECL_NEW, 1)
    if ns.read_text() != nsrc or umount.read_text() != usrc:
        raise RuntimeError("Source changed during patch")
    ns.write_text(new_ns)
    umount.write_text(new_umount)
    return True

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("kernel", type=Path)
    p.add_argument("kernelsu", type=Path)
    args = p.parse_args()
    print("[UMOUNT 4.19]", "applied" if patch(args.kernel.resolve(), args.kernelsu.resolve()) else "already applied")
