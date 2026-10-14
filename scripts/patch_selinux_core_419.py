#!/usr/bin/env python3
"""Integrate a serialized SELinux policy editing transaction into umi 4.19.

Patches the pinned LineageOS kernel sources (not the official KernelSU files).
This is an experimental compile/runtime adapter; real-boot safety and policy
snapshot validation must still pass before flashing.
"""
from pathlib import Path
import argparse

MARKER="UMI_KSU_419_SELINUX_TXN"
LOAD="int security_load_policy(struct selinux_state *state, void *data, size_t len)"
NEWLOAD="static int ksu_security_load_policy_unlocked(struct selinux_state *state, void *data, size_t len)"
NEXT="size_t security_policydb_len(struct selinux_state *state)"
DECLARE="int security_load_policy(struct selinux_state *state,"

INSERT=r"""
/* UMI_KSU_419_SELINUX_TXN: serialize kernel-driven edits and selinuxfs loads. */
#ifdef CONFIG_KSU
static DEFINE_MUTEX(ksu_legacy_policy_mutex);
#define KSU_POLICY_MAX_SIZE (64U * 1024U * 1024U)

/*
 * All policy loads on this kernel pass through this wrapper, including
 * selinuxfs and KernelSU. Read/modify/publish is a single serialized
 * transaction; security_load_policy_unlocked remains the stock implementation
 * including policydb/SID conversion and AVC update.
 */
int security_load_policy(struct selinux_state *state, void *data, size_t len)
{
    int result;

    mutex_lock(&ksu_legacy_policy_mutex);
    result = ksu_security_load_policy_unlocked(state, data, len);
    mutex_unlock(&ksu_legacy_policy_mutex);
    return result;
}

int ksu_legacy_policy_transaction(int (*edit)(struct policydb *, void *),
                                  void *opaque)
{
    struct selinux_state *state = &selinux_state;
    struct policydb *candidate = NULL;
    struct policy_file input, output;
    void *snapshot = NULL, *blob = NULL;
    size_t snapshot_len = 0, capacity, final_len = 0;
    int ret;

    if (!edit)
        return -EINVAL;

    mutex_lock(&ksu_legacy_policy_mutex);
    if (!selinux_initialized(state)) {
        ret = -EAGAIN;
        goto out;
    }
    ret = security_read_policy(state, &snapshot, &snapshot_len);
    if (ret)
        goto out;
    if (!snapshot_len || snapshot_len > KSU_POLICY_MAX_SIZE) {
        ret = -E2BIG;
        goto out;
    }
    candidate = kzalloc(sizeof(*candidate), GFP_KERNEL);
    if (!candidate) {
        ret = -ENOMEM;
        goto out;
    }
    input.data = snapshot;
    input.len = snapshot_len;
    ret = policydb_read(candidate, &input);
    if (ret)
        goto out; /* policydb_read destroys itself on error */
    candidate->len = snapshot_len;

    ret = edit(candidate, opaque);
    if (ret)
        goto out_destroy;

    /*
     * policydb_write is bounded by the policy_file's remaining length and
     * returns -EINVAL on insufficient capacity. Never publish partial data.
     * Reserve additional space for new KernelSU types/rules, then expand if
     * necessary; maximum size matches the stock selinuxfs policy load limit.
     */
    capacity = snapshot_len + min_t(size_t, snapshot_len, 1024U * 1024U);
    if (capacity > KSU_POLICY_MAX_SIZE)
        capacity = KSU_POLICY_MAX_SIZE;
    for (;;) {
        blob = vmalloc(capacity);
        if (!blob) {
            ret = -ENOMEM;
            goto out_destroy;
        }
        output.data = blob;
        output.len = capacity;
        ret = policydb_write(candidate, &output);
        if (!ret) {
            final_len = capacity - output.len;
            break;
        }
        vfree(blob);
        blob = NULL;
        if (ret != -EINVAL || capacity == KSU_POLICY_MAX_SIZE)
            goto out_destroy;
        capacity = min_t(size_t, capacity * 2, KSU_POLICY_MAX_SIZE);
    }

    if (!final_len) {
        ret = -EINVAL;
        goto out_destroy;
    }

    /* Stock loader converts SID tables, publishes atomically under its
     * policy_rwlock, flushes AVC, and notifies policy listeners.
     */
    ret = ksu_security_load_policy_unlocked(state, blob, final_len);
out_destroy:
    policydb_destroy(candidate);
out:
    vfree(blob);
    vfree(snapshot);
    kfree(candidate);
    mutex_unlock(&ksu_legacy_policy_mutex);
    return ret;
}
#else
/* The wrapper has no extra behavior in non-KernelSU configurations. */
int security_load_policy(struct selinux_state *state, void *data, size_t len)
{
    return ksu_security_load_policy_unlocked(state, data, len);
}
#endif

"""
PROTOTYPE=r"""
/* UMI_KSU_419_SELINUX_TXN: unique legacy API, not a selinux_policy alias. */
#ifdef CONFIG_KSU
struct policydb;
int ksu_legacy_policy_transaction(int (*edit)(struct policydb *, void *),
                                  void *opaque);
#endif
"""

def replace_once(src,old,new):
    if src.count(old)!=1:
        raise ValueError("Upstream mismatch: "+old)
    return src.replace(old,new,1)

def patch(kernel:Path):
    service=kernel/"security/selinux/ss/services.c"
    header=kernel/"security/selinux/include/security.h"
    origin=service.read_text()
    orig_h=header.read_text()
    if MARKER in origin:
        return False
    patched=replace_once(origin,LOAD,NEWLOAD)
    if NEXT not in patched:
        raise ValueError("No security_policydb_len anchor")
    patched=replace_once(patched,NEXT,INSERT+NEXT)
    if DECLARE not in orig_h:
        raise ValueError("SELinux header load prototype missing")
    patched_h=replace_once(orig_h,DECLARE,PROTOTYPE+"\n"+DECLARE)
    if service.read_text()!=origin or header.read_text()!=orig_h:
        raise RuntimeError("Files changed mid-patch")
    service.write_text(patched)
    header.write_text(patched_h)
    return True

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("kernel",type=Path)
    args=p.parse_args()
    print("[SELINUX CORE] ","patched" if patch(args.kernel.resolve()) else "already patched")
