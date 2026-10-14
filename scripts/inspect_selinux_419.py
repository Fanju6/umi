#!/usr/bin/env python3
"""Inspect native Linux 4.19 SELinux policy transaction APIs.

Signature checks aren't safety proofs; modern KernelSU publisher stays BLOCKED.
"""
import argparse
import json
from pathlib import Path

def read(root, path):
    return (root / path).read_text(errors="replace")

def inspect(kernel, kernelsu):
    hdr = read(kernel, "security/selinux/include/security.h")
    service = read(kernel, "security/selinux/ss/services.c")
    state = read(kernel, "security/selinux/ss/services.h")
    ksu = kernelsu / "kernel" if (kernelsu/"kernel/Kbuild").is_file() else kernelsu
    rules = read(ksu, "selinux/rules.c")
    requirements = {
        "legacy-state": "struct selinux_ss *ss;" in hdr and "policy_rwlock" in state,
        "snapshot": "int security_read_policy(struct selinux_state *state" in service
            and "read_lock(&state->ss->policy_rwlock)" in service
            and "policydb_write(policydb, &fp)" in service,
        "reload": "int security_load_policy(struct selinux_state *state" in service
            and "write_lock_irq(&state->ss->policy_rwlock)" in service
            and "sidtab_convert(oldsidtab, &convert_params)" in service
            and "avc_ss_reset(state->avc, seqno)" in service,
    }
    return {
        "native_api": "FOUND" if all(requirements.values()) else "MISSING",
        "checks": requirements,
        "kernelsu_publisher": "INCOMPATIBLE" if "selinux_state.policy_mutex" in rules else "NEEDS_REVIEW",
        "publish_ready": False,
        "note": "Implement serialized 4.19 policydb edits and native reload; never alias the incompatible struct layouts."
    }

if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("kernel",type=Path)
    p.add_argument("kernelsu",type=Path)
    p.add_argument("--require-native",action="store_true")
    args=p.parse_args()
    result=inspect(args.kernel,args.kernelsu)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    if args.require_native and result["native_api"]!="FOUND":
        raise SystemExit(2)
