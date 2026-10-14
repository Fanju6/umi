#!/usr/bin/env python3
"""Linux 4.19-only adaptations for official KernelSU v3.3.0.

No function-pointer casts; strict expected-source matching, atomic per-file writes
after all substitutions have validated.
"""
import argparse
from pathlib import Path

MARKER_MOUNT = "UMI_KSU_419_MOUNT_COMPAT"
MARKER_FSNOTIFY = "UMI_KSU_419_FSNOTIFY_COMPAT"

def once(source, needle, replacement, label):
    if source.count(needle) != 1:
        raise ValueError("Upstream mismatch: " + label)
    return source.replace(needle, replacement, 1)

def patch(root):
    root = root / "kernel" if (root / "kernel/Kbuild").is_file() else root
    if not (root / "Kbuild").is_file():
        raise ValueError("Not a KernelSU kernel/ directory")
    mnt = root / "infra/su_mount_ns.c"
    obs = root / "manager/pkg_observer.c"
    original_mount = mnt.read_text()
    original_obs = obs.read_text()
    mount = original_mount
    observer = original_obs
    if MARKER_MOUNT not in mount:
        mount = once(mount, "#include <uapi/linux/mount.h>",
            "/* UMI_KSU_419_MOUNT_COMPAT */\n"
            "#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 9, 0)\n"
            "#include <linux/mount.h>\n#include <linux/uaccess.h>\n"
            "#else\n#include <uapi/linux/mount.h>\n#endif", "mount include")
        mount = once(mount,
            "    int pm_ret = path_mount(NULL, &root_path, NULL, MS_PRIVATE | MS_REC, NULL);",
            """    int pm_ret;
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 9, 0)
    /*
     * do_mount() on 4.19 resolves dir_name via user_path(). Here the path is
     * a kernel string, so switch per-task address limit only for that call.
     * Restore it unconditionally before continuing.
     */
    mm_segment_t old_fs = get_fs();
    set_fs(KERNEL_DS);
    pm_ret = do_mount(NULL, (const char __user *)"/", NULL, MS_PRIVATE | MS_REC, NULL);
    set_fs(old_fs);
#else
    pm_ret = path_mount(NULL, &root_path, NULL, MS_PRIVATE | MS_REC, NULL);
#endif""", "mount operation")
    if MARKER_FSNOTIFY not in observer:
        oldfn="""static int ksu_handle_inode_event(struct fsnotify_mark *mark, u32 mask, struct inode *inode, struct inode *dir,
                                  const struct qstr *file_name, u32 cookie)"""
        newfn="""/* UMI_KSU_419_FSNOTIFY_COMPAT: handle_event ABI before modern fsnotify. */
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 9, 0)
static int ksu_handle_event(struct fsnotify_group *group, struct inode *inode,
                            u32 mask, const void *data, int data_type,
                            const unsigned char *file_name, u32 cookie,
                            struct fsnotify_iter_info *iter_info)
#else
static int ksu_handle_inode_event(struct fsnotify_mark *mark, u32 mask, struct inode *inode, struct inode *dir,
                                  const struct qstr *file_name, u32 cookie)
#endif"""
        observer=once(observer,oldfn,newfn,"fsnotify callback signature")
        observer=once(observer,
            '    if (file_name->len == 13 && !memcmp(file_name->name, "packages.list", 13)) {',
            """#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 9, 0)
    if (!strcmp((const char *)file_name, "packages.list")) {
#else
    if (file_name->len == 13 && !memcmp(file_name->name, "packages.list", 13)) {
#endif""", "fsnotify filename check")
        observer=once(observer,
            "static const struct fsnotify_ops ksu_ops = {\n    .handle_inode_event = ksu_handle_inode_event,\n};",
            """static const struct fsnotify_ops ksu_ops = {
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 9, 0)
    .handle_event = ksu_handle_event,
#else
    .handle_inode_event = ksu_handle_inode_event,
#endif
};""", "fsnotify ops struct")
    if mnt.read_text() != original_mount or obs.read_text() != original_obs:
        raise RuntimeError("Sources changed during patch preparation")
    if mount != original_mount:
        mnt.write_text(mount)
    if observer != original_obs:
        obs.write_text(observer)
    return mount != original_mount, observer != original_obs

if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("kernelsu", type=Path)
    args = a.parse_args()
    print("Linux 4.19 mount/fsnotify patches:", patch(args.kernelsu.resolve()))
