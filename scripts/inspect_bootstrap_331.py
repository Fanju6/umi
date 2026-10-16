#!/usr/bin/env python3
"""Verify v3.3.1 first-install bootstrap contract without pretending to prove it.

This check is read-only. It documents the possible seccomp FD acquisition
failure path and intentionally keeps fresh-install testing an open blocker.
"""
import argparse
import json
from pathlib import Path

MAIN = "manager/app/src/main/java/me/weishu/kernelsu/ui/MainActivity.kt"
CLI = "manager/app/src/main/java/me/weishu/kernelsu/ui/util/KsuCli.kt"
CALLS = "userspace/ksud/src/ksucalls.rs"
SETUID = "kernel/hook/setuid_hook.c"
SUPERCALL = "kernel/supercall/supercall.c"
KSUD_H = "kernel/runtime/ksud.h"
SHIM = "kernel/infra/seccomp_cache.c"
PTRACE = "arch/arm64/kernel/ptrace.c"


def inspect(kernel: Path, ksu: Path) -> dict:
    def contents(root, path):
        return (root / path).read_text(encoding="utf-8", errors="replace")

    main = contents(ksu, MAIN)
    cli = contents(ksu, CLI)
    calls = contents(ksu, CALLS)
    setuid = contents(ksu, SETUID)
    supercall = contents(ksu, SUPERCALL)
    ksud_header = contents(ksu, KSUD_H)
    shim = contents(ksu, SHIM)
    ptrace = contents(kernel, PTRACE)

    checks = {
        "manager_calls_install_on_first_ui": (
            "Natives.kernelUAPIVersion == Natives.managerUAPIVersion" in main
            and "install()" in main
        ),
        "manager_launches_bundled_ksud_for_root": (
            "libksud.so" in cli and '"debug", "su"' in cli
        ),
        "kernel_requires_data_ksud_path": '#define KSUD_PATH "/data/adb/ksud"' in ksud_header,
        "ksud_reboot_magic_fallback_exists": (
            "libc::SYS_reboot" in calls
            and "KSU_INSTALL_MAGIC1" in calls
            and "KSU_INSTALL_MAGIC2" in calls
        ),
        "ksud_logs_seccomp_denial": (
            "KernelSU driver install syscall was blocked by seccomp" in calls
        ),
        "manager_injected_fd_has_close_on_exec": (
            "ksu_install_fd_with_permissions(O_CLOEXEC, 0)" in supercall
            and "ksu_install_fd();" in setuid
        ),
        "legacy_noop_seccomp_cache": (
            "UMI_KSU_419_NO_ACTION_CACHE" in shim
            and "void ksu_seccomp_allow_cache" in shim
        ),
        "legacy_seccomp_before_tracepoint": (
            ptrace.find("secure_computing(NULL)") >= 0
            and ptrace.find("trace_sys_enter(regs, regs->syscallno)") >= 0
            and ptrace.find("secure_computing(NULL)")
                < ptrace.find("trace_sys_enter(regs, regs->syscallno)")
        ),
    }
    return {
        "supported_version": "v3.3.1",
        "upstream_contract_checks": checks,
        "source_contract_passed": all(checks.values()),
        "first_install_without_debugging_verified": False,
        "release_blocked_for_first_install": True,
        "hypothesis": (
            "Manager libksud child loses CLOEXEC injected fd; reboot-magic "
            "fallback may be filtered by Android 16 seccomp on Linux 4.19. "
            "Runtime SIGSYS/errno evidence is needed; source pattern alone "
            "is not proof. Do not clear the release blocker based on CI."
        ),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("kernel", type=Path)
    p.add_argument("ksu", type=Path)
    p.add_argument("--require-source", action="store_true")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    report = inspect(a.kernel.resolve(), a.ksu.resolve())
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if a.output:
        a.output.write_text(rendered + "\n", encoding="utf-8")
    if a.require_source and not report["source_contract_passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
