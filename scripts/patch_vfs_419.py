#!/usr/bin/env python3
"""Targeted, fail-closed VFS adaptation for official KernelSU v3.3.0 on Linux 4.19."""
from pathlib import Path
import argparse

MARKER = "UMI_KSU_419_VFS_COMPAT"

def only(text, old, new, reason):
    if text.count(old) != 1:
        raise ValueError("Upstream mismatch: " + reason)
    return text.replace(old, new, 1)

def patch(root):
    root = root / "kernel" if (root / "kernel/Kbuild").is_file() else root
    if not (root / "Kbuild").is_file():
        raise ValueError("Not a KernelSU source directory")
    path = root / "infra/file_wrapper.c"
    original = path.read_text()
    if MARKER in original:
        return False
    src = original
    src = only(src,
      "#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 1, 0)\nstatic int ksu_wrapper_iopoll",
      "/* UMI_KSU_419_VFS_COMPAT: 4.19 file_operations lacks iopoll. */\n"
      "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 0, 0)\n"
      "#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 1, 0)\nstatic int ksu_wrapper_iopoll",
      "iopoll beginning")
    src = only(src, "    return orig->f_op->iopoll(kiocb, spin);\n}\n#endif",
      "    return orig->f_op->iopoll(kiocb, spin);\n}\n#endif\n#endif /* old VFS iopoll */",
      "iopoll end")
    src = only(src,
      "// no REMAP_FILE_DEDUP: use file_in",
      "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 0, 0)\n// no REMAP_FILE_DEDUP: use file_in",
      "remap start")
    compat = """#else /* Linux 4.19 uses separate clone and dedupe operations. */
static int ksu_wrapper_clone_file_range(struct file *file_in, loff_t pos_in,
                                        struct file *file_out, loff_t pos_out, u64 len)
{
    struct ksu_file_wrapper *data = file_in->private_data;
    struct file *orig = data->orig;
    if (!orig->f_op->clone_file_range)
        return -EOPNOTSUPP;
    return orig->f_op->clone_file_range(orig, pos_in, file_out, pos_out, len);
}

static int ksu_wrapper_dedupe_file_range(struct file *file_in, loff_t pos_in,
                                         struct file *file_out, loff_t pos_out, u64 len)
{
    struct ksu_file_wrapper *data = file_out->private_data;
    struct file *orig = data->orig;
    if (!orig->f_op->dedupe_file_range)
        return -EOPNOTSUPP;
    return orig->f_op->dedupe_file_range(file_in, pos_in, orig, pos_out, len);
}
#endif /* VFS remap/clone/dedupe */

"""
    src = only(src,
      "static int ksu_wrapper_fadvise(struct file *fp, loff_t off1, loff_t off2, int flags)",
      compat + "static int ksu_wrapper_fadvise(struct file *fp, loff_t off1, loff_t off2, int flags)",
      "remap end")
    src = only(src, "    p->ops.iopoll = fp->f_op->iopoll ? ksu_wrapper_iopoll : NULL;",
      "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 0, 0)\n"
      "    p->ops.iopoll = fp->f_op->iopoll ? ksu_wrapper_iopoll : NULL;\n#endif",
      "iopoll field")
    src = only(src,
      "    p->ops.remap_file_range = fp->f_op->remap_file_range ? ksu_wrapper_remap_file_range : NULL;",
      "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 0, 0)\n"
      "    p->ops.remap_file_range = fp->f_op->remap_file_range ? ksu_wrapper_remap_file_range : NULL;\n"
      "#else\n"
      "    p->ops.clone_file_range = fp->f_op->clone_file_range ? ksu_wrapper_clone_file_range : NULL;\n"
      "    p->ops.dedupe_file_range = fp->f_op->dedupe_file_range ? ksu_wrapper_dedupe_file_range : NULL;\n"
      "#endif", "clone/dedupe fields")
    path.write_text(src)
    return True

if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("kernelsu", type=Path)
    args = a.parse_args()
    print("[VFS] patch " + ("applied" if patch(args.kernelsu.resolve()) else "already applied"))
