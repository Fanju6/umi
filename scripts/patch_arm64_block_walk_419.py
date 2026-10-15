#!/usr/bin/env python3
"""Fix the arm64 Linux 4.19 block-mapping page-table walk in KernelSU.

The pinned umi 4.19 pgtable.h defines pmd_bad() as !PMD_TABLE_BIT. A
PMD_TYPE_SECT block is therefore NOT a bad mapping, but KernelSU's
phys_from_virt() rejects it if pmd_sect() is not checked first.
The upstream patch_memory.c only guards pmd_leaf()/pud_leaf() using
defined(), which does not detect the 4.19 pmd_sect()/pud_sect() helpers.

Only edit exact, known source spans. Refuse unknown revisions. This fixes a
specific address translation defect; it does NOT establish that writing to
the syscall table or enabling root is safe on a real phone.
"""
import argparse
from pathlib import Path

MARKER = "UMI_KSU_419_ARM64_BLOCK_WALK"

INCLUDE_ANCHOR = '#include "asm-generic/fixmap.h"'
INCLUDE_PATCHED = (
    '#include "asm-generic/fixmap.h"\n'
    '/* UMI_KSU_419_ARM64_BLOCK_WALK */\n'
    '#include <linux/version.h>'
)

OLD_PUD = """    pud = pud_offset(p4d, addr);
    if (pud_none(*pud) || pud_bad(*pud))
        goto fail;
    pr_debug("pud of 0x%lx p=0x%lx v=0x%lx", addr, (uintptr_t)pud, (uintptr_t)pud_val(*pud));
#if defined(pud_leaf)
    if (pud_leaf(*pud)) {
"""
NEW_PUD = """    pud = pud_offset(p4d, addr);
    if (pud_none(*pud))
        goto fail;
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 10, 0)
    /*
     * Linux 4.19 arm64: pud_bad() requires PUD_TABLE_BIT. A valid
     * PUD_TYPE_SECT block is not a table, so check block FIRST.
     */
    if (pud_sect(*pud))
        return __pud_to_phys(*pud) + (addr & ~PUD_MASK);
#endif
    if (pud_bad(*pud))
        goto fail;
    pr_debug("pud of 0x%lx p=0x%lx v=0x%lx", addr, (uintptr_t)pud, (uintptr_t)pud_val(*pud));
#if defined(pud_leaf)
    if (pud_leaf(*pud)) {
"""

OLD_PMD = """    pmd = pmd_offset(pud, addr);
    pr_debug("pmd of 0x%lx p=0x%lx v=0x%lx", addr, (uintptr_t)pmd, (uintptr_t)pmd_val(*pmd));
#if defined(pmd_leaf)
    if (pmd_leaf(*pmd)) {
"""
NEW_PMD = """    pmd = pmd_offset(pud, addr);
    pr_debug("pmd of 0x%lx p=0x%lx v=0x%lx", addr, (uintptr_t)pmd, (uintptr_t)pmd_val(*pmd));
    if (pmd_none(*pmd))
        goto fail;
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 10, 0)
    /*
     * Linux 4.19 arm64: pmd_bad() sees a PMD_TYPE_SECT as bad because
     * PMD_TABLE_BIT is clear. Resolve the physical block base instead.
     */
    if (pmd_sect(*pmd))
        return __pmd_to_phys(*pmd) + (addr & ~PMD_MASK);
#endif
#if defined(pmd_leaf)
    if (pmd_leaf(*pmd)) {
"""

def patch(root: Path) -> bool:
    ksu = root / "kernel" if (root / "kernel/Kbuild").is_file() else root
    if not (ksu / "Kbuild").is_file():
        raise ValueError("Expected the pinned KernelSU checkout")
    target = ksu / "hook/arm64/patch_memory.c"
    original = target.read_text(encoding="utf-8")
    if MARKER in original:
        if (NEW_PUD not in original or NEW_PMD not in original
                or original.count(MARKER) != 1):
            raise ValueError("Partial arm64 mapping patch detected")
        return False
    anchors = ((INCLUDE_ANCHOR, INCLUDE_PATCHED),
               (OLD_PUD, NEW_PUD), (OLD_PMD, NEW_PMD))
    for old, _ in anchors:
        if original.count(old) != 1:
            raise ValueError("Unknown upstream patch_memory.c; expected source anchor missing")
    result = original
    for old, new in anchors:
        result = result.replace(old, new, 1)
    if target.read_text(encoding="utf-8") != original:
        raise RuntimeError("KernelSU file changed during preparation")
    target.write_text(result, encoding="utf-8")
    return True


def main():
    arg = argparse.ArgumentParser(description=__doc__)
    arg.add_argument("kernelsu", type=Path)
    a = arg.parse_args()
    print("[ARM64 BLOCK WALK]", "patched" if patch(a.kernelsu.resolve()) else "already patched")


if __name__ == "__main__":
    main()
