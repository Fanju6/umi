#!/usr/bin/env python3
"""umi Linux 6.12 / 7.0 P0 离线源码清单检查（只读，不下载，不编译，不刷机）。"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "config" / "mainline-research.json"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
VALID_ID = re.compile(r"^[a-z][a-z0-9_]*$")
SOURCE_KEYS = ("vendor_419", "mainline_612", "mainline_70", "dagu_reference")
COMPAT = re.compile(r"\bcompatible\s*=\s*([^;]+);", re.S)
STRINGS = re.compile(r'"([^"\n]+)"')


def _safe_relative(path: str) -> bool:
    p = Path(path)
    return bool(path) and not p.is_absolute() and ".." not in p.parts and "\\" not in path and not path.startswith("./")


def validate_manifest(data: dict) -> None:
    if data.get("schema_version") != 1 or data.get("target", {}).get("codename") != "umi":
        raise ValueError("manifest 的 schema_version / 目标设备不正确")
    sources = data.get("sources", {})
    if set(sources) != set(SOURCE_KEYS):
        raise ValueError("缺少或增加了未审核的源码基线")
    for key, source in sources.items():
        if not isinstance(source.get("url"), str) or not source["url"].startswith("https://github.com/"):
            raise ValueError(f"{key}：无效的可信源码 URL")
        if not SHA40.fullmatch(source.get("sha", "")):
            raise ValueError(f"{key}：固定 Git SHA 必须为完整 40 位小写十六进制")
        for field in ("required", "absent"):
            paths = source.get(field, [])
            if not isinstance(paths, list) or (field == "required" and not paths):
                raise ValueError(f"{key}：{field} 路径清单不完整")
            if len(set(paths)) != len(paths) or any(not isinstance(p, str) or not _safe_relative(p) for p in paths):
                raise ValueError(f"{key}：{field} 发现重复/越界/不安全路径")
    entries = data.get("observations", [])
    if len(entries) < 10 or len({x.get("id") for x in entries}) != len(entries):
        raise ValueError("设备子系统对照清单缺失或 ID 重复")
    for x in entries:
        if not VALID_ID.fullmatch(x.get("id", "")) or x.get("tier") not in ("P0", "P1", "P2"):
            raise ValueError("设备子系统 ID / 阶段有误")
    safety = data.get("safety", {})
    for field in ("safe_to_flash", "boot_image_available", "mainline_umi_dts_available", "android_boot_verified"):
        if safety.get(field) is not False:
            raise ValueError(f"研究阶段禁止将 {field} 标记为通过")


def read_head(root: Path) -> str:
    if not (root / ".git").exists():
        raise ValueError("不是可核对版本的 Git 检出目录")
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
        check=True, text=True, capture_output=True,
    )
    return result.stdout.strip()


def inspect_tree(root: Path, source: dict) -> dict:
    root = root.resolve()
    actual = read_head(root)
    expected = source["sha"]
    if actual != expected:
        return {"status": "sha_mismatch", "expected_sha": expected, "actual_sha": actual, "required_checked": False}
    present = [p for p in source["required"] if (root / p).is_file()]
    missing = [p for p in source["required"] if not (root / p).is_file()]
    wrongly_present = [p for p in source.get("absent", []) if (root / p).exists()]
    # 只报告源码中兼容字符串，不检查节点是否 enabled，也不证明对应驱动可用。
    compatible = set()
    for p in present:
        if Path(p).suffix not in (".dts", ".dtsi"):
            continue
        text = (root / p).read_text(encoding="utf-8", errors="replace")
        for match in COMPAT.finditer(text):
            compatible.update(STRINGS.findall(match.group(1)))
    status = "sources_present" if not missing and not wrongly_present else "file_matrix_mismatch"
    return {
        "status": status, "expected_sha": expected, "actual_sha": actual,
        "required_checked": True, "missing": missing, "unexpected": wrongly_present,
        "compatible_strings": sorted(compatible)[:150],
        "note": "兼容字符串为源码文本线索，不等于设备驱动已验证",
    }


def parse_root_args(items: list[str]) -> dict[str, Path]:
    roots = {}
    for item in items:
        if "=" not in item:
            raise ValueError("使用 --source source_key=/path 格式")
        key, location = item.split("=", 1)
        if key not in SOURCE_KEYS or key in roots or not location:
            raise ValueError(f"不支持或重复的源码名称：{key}")
        roots[key] = Path(location)
    return roots


def run(manifest: dict, roots: dict[str, Path], require_all: bool = False) -> tuple[dict, bool]:
    validate_manifest(manifest)
    result = {
        "target": "umi", "phase": "P0", "safe_to_flash": False,
        "android_boot_verified": False, "sources": {},
        "note": "仅静态源码检查，未扫描项不代表通过；不会下载、编译或刷写",
    }
    failed = False
    for key in SOURCE_KEYS:
        if key not in roots:
            result["sources"][key] = {"status": "not_scanned"}
            failed |= require_all
            continue
        try:
            d = inspect_tree(roots[key], manifest["sources"][key])
        except (ValueError, OSError, subprocess.CalledProcessError) as exc:
            d = {"status": "inspection_error", "reason": str(exc)}
        result["sources"][key] = d
        failed |= d["status"] != "sources_present"
    return result, not failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source", action="append", default=[], help="例如 vendor_419=/path/to/kernel")
    parser.add_argument("--require-all", action="store_true", help="要求四个锁定仓库均有实际 Git 检出")
    parser.add_argument("--output", type=Path, help="本地生成报告 JSON，不默认写文件")
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        roots = parse_root_args(args.source)
        result, ok = run(manifest, roots, require_all=args.require_all)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"P0 清单检查失败：{exc}", file=sys.stderr)
        return 2
    formatted = json.dumps(result, ensure_ascii=False, indent=2)
    print(formatted)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(formatted + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
