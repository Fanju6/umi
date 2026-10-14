#!/usr/bin/env python3
"""Compile-compatible SELinux policy transaction path for umi Linux 4.19.

Uses real policydb and native security_load_policy, no structural type aliases.
SELinux Hide remains disabled on 4.19 pending real backup SID semantics.
"""
from pathlib import Path
import argparse

MARKER = "UMI_KSU_419_RULES_TXN"
MARKER_SEPOL = "UMI_KSU_419_SEPOLICY_TXN"
MARKER_HIDE = "UMI_KSU_419_HIDE_UNSUPPORTED"

LEGACY_BATCH = r"""
/* 4.19: edit only a private candidate; the core service publishes atomically. */
struct ksu_legacy_sepol_data {
    const u8 *payload;
    size_t length;
    int success_count;
};

static int ksu_legacy_sepol_edit(struct policydb *db, void *opaque)
{
    struct ksu_legacy_sepol_data *data = opaque;
    struct sepol_batch_cursor cursor = {
        .cur = data->payload,
        .end = data->payload + data->length,
    };
    u32 cmd_index = 0;
    int ret;

    data->success_count = 0;
    while (cursor.cur < cursor.end) {
        struct sepol_data header;
        const char *args[KSU_SEPOLICY_MAX_ARGS] = { 0 };
        int argc;
        u32 i;

        ret = sepol_read_cmd_header(&cursor, &header);
        if (ret)
            return ret;
        argc = sepol_expected_argc(header.cmd);
        if (argc < 0 || argc > KSU_SEPOLICY_MAX_ARGS)
            return -EINVAL;
        for (i = 0; i < argc; ++i) {
            ret = sepol_read_string(&cursor, &args[i]);
            if (ret)
                return ret;
        }
        ret = apply_one_sepolicy_cmd(db, &header, args);
        if (!ret)
            data->success_count++;
        else
            pr_warn("ksu: sepolicy command %u failed (%d)\n",
                    cmd_index, ret);
        cmd_index++;
    }
    return 0;
}

int handle_sepolicy(void __user *user_data, u64 data_len)
{
    struct ksu_legacy_sepol_data batch;
    u8 *payload;
    int ret;

    if (!user_data || !data_len)
        return -EINVAL;
    if (data_len > KSU_SEPOLICY_MAX_BATCH_SIZE)
        return -E2BIG;
    payload = kvmalloc((size_t)data_len, GFP_KERNEL);
    if (!payload)
        return -ENOMEM;
    if (copy_from_user(payload, user_data, (size_t)data_len)) {
        ret = -EFAULT;
        goto out;
    }
    batch.payload = payload;
    batch.length = (size_t)data_len;
    batch.success_count = 0;
    ret = ksu_legacy_policy_transaction(ksu_legacy_sepol_edit, &batch);
    if (!ret)
        ret = batch.success_count;
out:
    kvfree(payload);
    return ret;
}
"""

LEGACY_HIDE=r"""/* UMI_KSU_419_HIDE_UNSUPPORTED: no fake selinux_policy or SID aliases. */
#include <linux/version.h>
#include <linux/errno.h>
#include <linux/printk.h>
#include "selinux_hide.h"

/*
 * 4.19 has selinux_state.ss, not a modern selinux_policy snapshot.
 * Enabling SELinux Hide without independent SID mapping is unsafe; leave
 * the optional feature unregistered and do not intercept SELinux syscalls.
 */
void ksu_selinux_hide_init(void)
{
    pr_info("KernelSU: SELinux Hide unavailable on legacy 4.19\n");
}
void ksu_selinux_hide_exit(void) {}
void ksu_selinux_hide_drop_backup_if_unused(void) {}
void ksu_selinux_hide_handle_second_stage(void) {}
void ksu_selinux_hide_handle_post_fs_data(void) {}
"""

def replace_once(src, old, new, label):
    if src.count(old) != 1:
        raise ValueError("Upstream mismatch: " + label)
    return src.replace(old,new,1)

def patch(ksu:Path):
    root=ksu/"kernel" if (ksu/"kernel/Kbuild").is_file() else ksu
    if not (root/"Kbuild").is_file():
        raise ValueError("Not KernelSU checkout")
    rfile=root/"selinux/rules.c"
    pfile=root/"selinux/sepolicy.c"
    hfile=root/"feature/selinux_hide.c"
    original=rfile.read_text()
    oldpol=pfile.read_text()
    oldhide=hfile.read_text()
    if MARKER in original:
        return False

    start=original.find("    ksu_type(db, KERNEL_SU_DOMAIN, \"domain\");")
    end=original.find("    rcu_assign_pointer(selinux_state.policy, pol);",start)
    if start < 0 or end <= start:
        raise ValueError("Default rules block not found")
    edits=original[start:end]
    intro=original.find("void apply_kernelsu_rules()")
    stop=original.find("#define KSU_SEPOLICY_MAX_BATCH_SIZE",intro)
    if intro<0 or stop<0 or intro>=stop:
        raise ValueError("Cannot isolate default rules")
    original_default=original[intro:stop]
    if "reset_avc_cache();" not in original_default or "mutex_unlock(&selinux_state.policy_mutex)" not in original_default:
        raise ValueError("Modern publisher changed")
    legacy_default=(
        "/* UMI_KSU_419_RULES_TXN */\n"
        "static int ksu_legacy_default_rules(struct policydb *db, void *opaque)\n{\n"
        "    (void)opaque;\n"
        "    if (!ksu_type(db, KERNEL_SU_DOMAIN, \"domain\") ||\n"
        "        !ksu_type(db, KERNEL_SU_FILE, \"file_type\"))\n"
        "        return -EINVAL;\n"
        + edits +
        "    return 0;\n}\n"
        "void apply_kernelsu_rules(void)\n{\n"
        "    int ret = ksu_legacy_policy_transaction(ksu_legacy_default_rules, NULL);\n"
        "    if (ret)\n"
        "        pr_err(\"KernelSU: 4.19 default SELinux transaction failed: %d\\n\", ret);\n"
        "}\n"
    )
    patched = original[:intro]+("#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 10, 0)\n"+
                                legacy_default+"#else\n"+original_default+"#endif\n\n")+original[stop:]
    start_batch=patched.find("int handle_sepolicy(void __user *user_data, u64 data_len)")
    if start_batch<0 or patched.count("int handle_sepolicy(void __user *user_data, u64 data_len)")!=1:
        raise ValueError("handle_sepolicy signature changed")
    modern_batch=patched[start_batch:]
    if "rcu_assign_pointer(selinux_state.policy, pol)" not in modern_batch:
        raise ValueError("Modern sepolicy publisher missing")
    patched=patched[:start_batch]+"#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n"+modern_batch+"\n#else\n"+LEGACY_BATCH+"\n#endif\n"

    anchor="void ksu_destroy_sepolicy(struct selinux_policy *pol)"
    if oldpol.count(anchor)!=1:
        raise ValueError("Cannot find policy implementation")
    policy=replace_once(oldpol,anchor,
          "/* "+MARKER_SEPOL+": modern policy objects do not exist in 4.19. */\n"
          "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n"+anchor,"modern policy functions")
    policy += "\n#endif /* 4.19 uses kernel-native policydb transaction */\n"
    if MARKER_HIDE in oldhide:
        raise ValueError("Hide source has already been changed")
    hide=LEGACY_HIDE+"\n#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n"+oldhide+"\n#endif /* legacy hide disabled */\n"
    for path,src in [(rfile,original),(pfile,oldpol),(hfile,oldhide)]:
        if path.read_text()!=src:
            raise RuntimeError("Sources changed during editing")
    for path,contents in [(rfile,patched),(pfile,policy),(hfile,hide)]:
        path.write_text(contents)
    return True

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("kernelsu",type=Path)
    a=p.parse_args()
    print("[LEGACY RULES] "+"patched" if patch(a.kernelsu.resolve()) else "already patched")
