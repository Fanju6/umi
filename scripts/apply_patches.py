#!/usr/bin/env python3
"""按官方 KernelSU 锁定版本统一执行 umi Linux 4.19 兼容补丁。

只对 prepare_sources.sh 已准备、且 Git SHA 与 config/upstream.env 匹配的源码执行。
任何补丁失败即停止；不执行刷机操作、不修改源码锁定版本。
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINS = {
    "v3.3.0": "932014ab5b2c9b74a3d11e2ec4d17dd10fc9442e",
    "v3.3.1": "0c0fdb960178fa12d80d6cbcfdcb6ad8be6a865d",
}
LINEAGE_SHA = "71b13e62f057a649b77fe4062feb73ee72ad609c"

# 顺序来自经整核编译及真机验证的 v3.3.1 分支；TEST2 保留原有 14 步。
PREFIX = (
    ("apply_compat.py", ("ksu",)),
    ("patch_vfs_419.py", ("ksu",)),
    ("patch_legacy_apis.py", ("ksu",)),
    ("patch_policy_419.py", ("ksu",)),
)
V331_ONLY = (
    ("patch_task_work_331.py", ("ksu",)),
    ("patch_manager_postexec_fd_419.py", ("ksu",)),
)
SUFFIX = (
    ("patch_sulog_419.py", ("ksu",)),
    ("patch_dispatch_419.py", ("ksu",)),
    ("patch_syscall_failclosed_419.py", ("ksu",)),
    ("patch_arm64_block_walk_419.py", ("ksu",)),
    ("patch_avtab_419.py", ("ksu",)),
    ("patch_filename_419.py", ("ksu",)),
    ("patch_type_419.py", ("ksu",)),
    ("patch_selinux_core_419.py", ("kernel",)),
    ("patch_rules_419.py", ("ksu",)),
    ("patch_umount_419.py", ("kernel", "ksu")),
)


def load_pins(config: Path) -> dict[str, str]:
    values = {}
    for line in config.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Z][A-Z0-9_]*)=([A-Za-z0-9_.:/+-]+)", line)
        if not match:
            raise ValueError("上游配置格式不符合安全白名单")
        name, value = match.groups()
        if name in values:
            raise ValueError(f"重复的上游配置项：{name}")
        values[name] = value
    return values


def plan(ref: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if ref not in PINS:
        raise ValueError(f"不支持的 KernelSU 版本：{ref}")
    steps = PREFIX + (V331_ONLY if ref == "v3.3.1" else ()) + SUFFIX
    if len({entry[0] for entry in steps}) != len(steps):
        raise ValueError("兼容补丁执行清单存在重复")
    return steps


def validate_pins(values: dict[str, str], profile: str) -> str:
    ref = values.get("KSU_REF", "")
    if profile != "auto" and profile != ref:
        raise ValueError(f"指定 {profile} 与仓库锁定的 {ref} 不符，拒绝混用")
    if ref not in PINS or values.get("KSU_SHA") != PINS.get(ref):
        raise ValueError(f"KernelSU 上游版本或固定 SHA 不匹配：{ref}")
    if values.get("LINEAGE_KERNEL_SHA") != LINEAGE_SHA:
        raise ValueError("LineageOS umi 内核 SHA 与已验证基线不符")
    return ref


def git_sha(path: Path) -> str:
    output = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--verify", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    return output.stdout.strip()


def apply(workdir: Path, values: dict[str, str], steps) -> None:
    ksu = workdir / "KernelSU"
    kernel = workdir / "kernel"
    for name, path, expected in (
        ("KernelSU", ksu, values["KSU_SHA"]),
        ("LineageOS", kernel, values["LINEAGE_KERNEL_SHA"]),
    ):
        if not (path / ".git").exists() or git_sha(path) != expected:
            raise ValueError(f"{name} 源码未准备或 Git HEAD 不匹配：{path}")

    paths = {"ksu": ksu, "kernel": kernel}
    for i, (script, targets) in enumerate(steps, 1):
        args = [sys.executable, str(ROOT / "scripts" / script)] + [
            str(paths[target]) for target in targets
        ]
        print(f"[{i}/{len(steps)}] {script}", flush=True)
        subprocess.run(args, cwd=ROOT, check=True)
    print(f"兼容补丁执行成功：共 {len(steps)} 步", flush=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile", choices=("auto", *PINS.keys()), default="auto")
    p.add_argument("--workdir", type=Path, default=ROOT / ".work")
    p.add_argument("--plan", action="store_true", help="只核对固定上游和输出补丁计划")
    args = p.parse_args()
    try:
        values = load_pins(ROOT / "config" / "upstream.env")
        ref = validate_pins(values, args.profile)
        steps = plan(ref)
        if args.plan:
            print(f"官方 KernelSU {ref}，固定 SHA {values['KSU_SHA']}：")
            for i, (name, targets) in enumerate(steps, 1):
                print(f"{i:02d}. {name} ({', '.join(targets)})")
        else:
            apply(args.workdir.resolve(), values, steps)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"兼容补丁执行失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
