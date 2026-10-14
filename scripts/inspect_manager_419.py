#!/usr/bin/env python3
"""4.19 Manager 通道源代码检查，永不声称真机可用。"""
import argparse
import json
from pathlib import Path

def inspect(kernel:Path, ksu:Path) ->dict:
    root=ksu/"kernel" if (ksu/"kernel/Kbuild").is_file() else ksu
    entry=(kernel/"arch/arm64/kernel/ptrace.c").read_text(errors="replace")
    setuid=(root/"hook/setuid_hook.c").read_text(errors="replace")
    supercall=(root/"supercall/supercall.c").read_text(errors="replace")
    shim=(root/"infra/seccomp_cache.c").read_text(errors="replace")
    begin=entry.find("int syscall_trace_enter(struct pt_regs *regs)")
    end=entry.find("void syscall_trace_exit(", begin)
    block=entry[begin:end] if begin>=0 and end>begin else ""
    sec=block.find("secure_computing(NULL)")
    trace=block.find("trace_sys_enter(regs, regs->syscallno)")
    seccomp_first=sec>=0 and trace>=0 and sec<trace
    manager_inject=("is_uid_manager(new_uid)" in setuid and
                    "ksu_install_fd();" in setuid and
                    "fd_install(fd, filp)" in supercall)
    reboot_hook=("reboot_handler_pre" in supercall and
                 "register_kprobe(&reboot_kp)" in supercall)
    no_cache=("UMI_KSU_419_NO_ACTION_CACHE" in shim and
              "void ksu_seccomp_allow_cache" in shim)
    return {
        "kernel_entry_verified": seccomp_first,
        "seccomp_before_sys_enter": seccomp_first,
        "manager_fd_injection_source_present": manager_inject,
        "reboot_kprobe_source_present": reboot_hook,
        "legacy_action_cache_noop": no_cache,
        "manager_runtime_verified": False,
        "block_release": True,
        "reason": ("4.19 Seccomp runs before trace_sys_enter; direct Manager FD "
                   "injection needs Android 16 runtime/permissions testing. "
                   "Do not assume a reboot kprobe is reachable after Seccomp denial."),
    }

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("kernel",type=Path)
    p.add_argument("ksu",type=Path)
    p.add_argument("--require-source",action="store_true")
    args=p.parse_args()
    result=inspect(args.kernel,args.ksu)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    if args.require_source and not all((
            result["kernel_entry_verified"],
            result["manager_fd_injection_source_present"],
            result["reboot_kprobe_source_present"],
            result["legacy_action_cache_noop"])):
        raise SystemExit(2)
