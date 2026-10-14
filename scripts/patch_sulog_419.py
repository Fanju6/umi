#!/usr/bin/env python3
"""Minimal, fail-closed Linux 4.19 Sulog include compatibility for KernelSU 3.3.0."""
import argparse
from pathlib import Path

MARKER = "UMI_KSU_419_SULOG_INCLUDE"
UPSTREAM = "#include <linux/minmax.h>"
COMPAT = """/* UMI_KSU_419_SULOG_INCLUDE: min/max live in linux/kernel.h on 4.19. */
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 0, 0)
#include <linux/kernel.h>
#else
#include <linux/minmax.h>
#endif"""


def patch(root: Path) -> bool:
    kernel = root / "kernel" if (root / "kernel/Kbuild").is_file() else root
    if not (kernel / "Kbuild").is_file():
        raise ValueError("KernelSU kernel directory expected")
    source = kernel / "sulog/event.c"
    original = source.read_text(encoding="utf-8")
    if MARKER in original:
        return False
    if original.count(UPSTREAM) != 1:
        raise ValueError("KernelSU upstream changed: missing unique minmax.h include")
    # Linux version macros must be available before the conditional.
    original_include = "#include <asm/current.h>"
    if original.count(original_include) != 1:
        raise ValueError("KernelSU upstream changed: include anchor not found")
    fixed = original.replace(original_include,
                             "#include <linux/version.h>\n" + original_include, 1)
    fixed = fixed.replace(UPSTREAM, COMPAT, 1)
    source.write_text(fixed, encoding="utf-8")
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("kernelsu", type=Path)
    args = ap.parse_args()
    print("[SULOG] " + ("patched" if patch(args.kernelsu.resolve()) else "already patched"))
