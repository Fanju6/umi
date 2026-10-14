#!/usr/bin/env python3
"""Produce a compact compilation error summary; preserve the unabridged CI log."""
import argparse
import collections
import re
from pathlib import Path

PATTERN = re.compile(r"(?P<file>/[^ :]+):(?P<line>\d+):(?P<col>\d+): (?P<kind>fatal error|error): (?P<message>.+)")

def summarize(log: str) -> str:
    found = collections.Counter()
    for line in log.splitlines():
        m = PATTERN.search(line)
        if not m:
            continue
        path = m["file"].split("/drivers/kernelsu/")[-1]
        found[(path, m["message"])] += 1
    if not found:
        return "No Clang errors found; inspect the full build log for a toolchain or Kbuild error."
    parts = ["## KernelSU 4.19 编译错误", ""]
    for (path, msg), count in sorted(found.items()):
        parts.append(f"- \x60{path}\x60: {msg} ({count} 次)")
    return "\n".join(parts)

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("log", type=Path)
    args = p.parse_args()
    print(summarize(args.log.read_text(errors="replace")))
