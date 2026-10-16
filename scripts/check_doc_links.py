#!/usr/bin/env python3
"""校验当前维护入口的相对 Markdown 文件链接；只读、无网络。"""
import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

# 已归档的逐轮开发日志保留当时的原始路径，不按当前目录校验。
ENTRYPOINTS = (
    "README.md",
    "CONTRIBUTING.md",
    "docs/README.md",
    "docs/STATUS.md",
    "docs/BUILD.md",
    "docs/ARCHITECTURE.md",
    "docs/history/README.md",
)
LINK = re.compile(r"(?<!!)\[[^]\n]+\]\(([^\s)]+)(?:\s+['\"][^)]*['\"])?\)")


def check(root: Path, files=ENTRYPOINTS):
    root = root.resolve()
    errors = []
    count = 0
    for name in files:
        document = root / name
        if not document.is_file():
            errors.append(f"{name}: 导航文档不存在")
            continue
        for match in LINK.finditer(document.read_text(encoding="utf-8")):
            raw = match.group(1)
            parsed = urlsplit(raw)
            if parsed.scheme or parsed.netloc or raw.startswith(("#", "//", "/")):
                continue
            if not parsed.path:
                continue
            count += 1
            path = (document.parent / unquote(parsed.path)).resolve()
            if not path.is_relative_to(root):
                errors.append(f"{name}: 相对链接越出仓库：{raw}")
            elif not path.exists():
                errors.append(f"{name}: 目标不存在：{raw}")
    return count, errors


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = p.parse_args()
    count, errors = check(args.root)
    print(f"当前入口文档链接数量：{count}")
    for item in errors:
        print(f"ERROR: {item}", file=sys.stderr)
    if errors:
        raise SystemExit(1)
    print("所有当前入口文档的相对链接均有效")


if __name__ == "__main__":
    main()
