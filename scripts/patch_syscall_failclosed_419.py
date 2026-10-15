#!/usr/bin/env python3
"""Fail-closed arm64 KernelSU dispatcher installation on pinned Linux 4.19.

Real-world umi ramoops showed syscall table patching failed, but KernelSU still
announced slot 42 installed. sys_enter then redirected newfstatat(79) and
faccessat(48) into the unpatched ni_syscall slot, returning ENOSYS to Android
first-stage init. Do not redirect unless the table contains our dispatcher.

Source-specific and intentionally refuses unknown upstream revisions.
"""
import argparse
from pathlib import Path

MARKER = "UMI_KSU_419_DISPATCHER_FAIL_CLOSED"

OLD_HOOK = """    // Record for later restoration
    int i;
    bool found = false;
    for (i = 0; i < hooked_count; i++) {
        if (hooked_entries[i].nr == nr) {
            found = true;
            break;
        }
    }
    if (!found) {
        if (hooked_count < ARRAY_SIZE(hooked_entries)) {
            hooked_entries[hooked_count].nr = nr;
            hooked_entries[hooked_count].orig = orig;
            hooked_count++;
        } else {
            pr_warn("hooked_entries full, cannot track syscall %d for restoration\\n", nr);
        }
    }

    patch_syscall_table(nr, fn);

    mutex_unlock(&hooked_entries_lock);
"""

NEW_HOOK = """    /* UMI_KSU_419_DISPATCHER_FAIL_CLOSED:
     * NEVER record a hook or claim successful installation before verifying
     * that the underlying table patch succeeded.
     */
    int i;
    bool found = false;
    for (i = 0; i < hooked_count; i++) {
        if (hooked_entries[i].nr == nr) {
            found = true;
            break;
        }
    }
    if (!found && hooked_count >= ARRAY_SIZE(hooked_entries)) {
        pr_err("cannot track syscall %d; refusing untracked patch\\n", nr);
        mutex_unlock(&hooked_entries_lock);
        return;
    }
    if (patch_syscall_table(nr, fn)) {
        pr_err("syscall %d hook NOT installed; leaving table unchanged\\n", nr);
        mutex_unlock(&hooked_entries_lock);
        return;
    }
    if (!found) {
        hooked_entries[hooked_count].nr = nr;
        hooked_entries[hooked_count].orig = orig;
        hooked_count++;
    }

    mutex_unlock(&hooked_entries_lock);
"""

OLD_INIT = """    ksu_dispatcher_nr = ni_slot;
    ksu_syscall_table_hook(ksu_dispatcher_nr, (syscall_fn_t)ksu_syscall_dispatcher, NULL);
    pr_info("dispatcher installed at slot %d\\n", ksu_dispatcher_nr);
"""

NEW_INIT = """    /* Mark dispatcher active ONLY after confirming the syscall table entry
     * actually changed. Old 4.19 rodata may reject the write; enabling the
     * tracepoint in that state sends newfstatat/faccessat to -ENOSYS.
     */
    ksu_syscall_table_hook(ni_slot, (syscall_fn_t)ksu_syscall_dispatcher, NULL);
    if (READ_ONCE(ksu_syscall_table[ni_slot]) !=
        (syscall_fn_t)ksu_syscall_dispatcher) {
        WRITE_ONCE(ksu_dispatcher_nr, -1);
        pr_err("dispatcher patch failed; disabled syscall redirection (slot=%d)\\n",
               ni_slot);
        return;
    }
    WRITE_ONCE(ksu_dispatcher_nr, ni_slot);
    pr_info("dispatcher verified at slot %d\\n", ni_slot);
"""


def patch(ksu: Path) -> bool:
    root = ksu / "kernel" if (ksu / "kernel" / "Kbuild").is_file() else ksu
    if not (root / "Kbuild").is_file():
        raise ValueError("Not a pinned official KernelSU source tree")
    target = root / "hook" / "arm64" / "syscall_hook.c"
    original = target.read_text(encoding="utf-8")
    if MARKER in original:
        if "dispatcher verified at slot" not in original or "syscall redirection" not in original:
            raise ValueError("Partial dispatcher patch: refusing to continue")
        return False
    if original.count(OLD_HOOK) != 1 or original.count(OLD_INIT) != 1:
        raise ValueError("Unexpected official KernelSU v3.3.0 arm64 hook implementation")
    modified = original.replace(OLD_HOOK, NEW_HOOK, 1).replace(OLD_INIT, NEW_INIT, 1)
    if target.read_text(encoding="utf-8") != original:
        raise RuntimeError("Source changed during patch")
    target.write_text(modified, encoding="utf-8")
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("kernelsu", type=Path)
    a = p.parse_args()
    print("[DISPATCHER]", "fail-closed patch applied" if patch(a.kernelsu.resolve()) else "already patched")


if __name__ == "__main__":
    main()
