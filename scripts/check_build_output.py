#!/usr/bin/env python3
"""检查完整链接的内核产物；不会生成或发布 boot.img。"""
import argparse
import json
import hashlib
from pathlib import Path

def check_output(mode: str, out: Path) -> dict:
    if mode not in ("ksu", "baseline"):
        raise ValueError("mode must be ksu or baseline")
    config_file = out / ".config"
    if not config_file.is_file():
        raise FileNotFoundError(config_file)
    config = set(config_file.read_text(errors="replace").splitlines())

    required = {"CONFIG_EXT4_FS=y", "CONFIG_SECURITY_SELINUX=y"}
    if mode == "ksu":
        required |= {"CONFIG_KSU=y", "CONFIG_KPROBES=y"}
    else:
        required |= {"# CONFIG_KSU is not set"}
    missing = sorted(required - config)

    image = out / "arch/arm64/boot/Image"
    elf = out / "vmlinux"
    artifacts = {
        "Image": image.is_file() and image.stat().st_size > 1024 * 1024,
        "vmlinux": elf.is_file() and elf.stat().st_size > 1024 * 1024,
        "dtbs": any((out / "arch/arm64/boot/dts").rglob("*.dtb")),
        "umi-dtbo": (
            (out / "arch/arm64/boot/dts/vendor/qcom/umi-sm8250-overlay.dtbo").is_file()
            and (out / "arch/arm64/boot/dts/vendor/qcom/umi-sm8250-overlay.dtbo").stat().st_size > 0
        ),
    }
    if mode == "ksu":
        archive = out / "drivers/kernelsu/built-in.a"
        artifacts["KernelSU-archive"] = archive.is_file() and archive.stat().st_size > 0
    def sha256(path: Path) -> str | None:
        if not path.is_file():
            return None
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    return {
        "image_sha256": sha256(image),
        "umi_dtbo_sha256": sha256(out / "arch/arm64/boot/dts/vendor/qcom/umi-sm8250-overlay.dtbo"),
        "mode": mode,
        "passed": not missing and all(artifacts.values()),
        "required_config_missing": missing,
        "artifacts": artifacts,
        "note": "这仅是构建产物检查；不代表 boot.img 可刷机或 KernelSU 真机正常。",
    }

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["ksu","baseline"])
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    report=check_output(args.mode,args.output.resolve())
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if not report["passed"]:
        raise SystemExit(1)
